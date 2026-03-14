"""
Whale Watcher — Real-Time Trade Monitor for Polymarket Whales
==============================================================
Dual-source whale trade detection:
  1. Polygon WebSocket: subscribes to OrderFilled events on CTF Exchange (~2-3s latency)
  2. Data API Polling: polls activity every 5s as fallback + enrichment (~5-10s latency)

Usage:
    watcher = WhaleWatcher()
    watcher.start()
    # ... later ...
    trades = watcher.get_recent_trades(max_age=300)
    watcher.stop()
"""

import asyncio
import collections
import hashlib
import json
import threading
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime


# =====================
# CONSTANTS
# =====================

# Polymarket CTF Exchange on Polygon (all trades go through this contract)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

# Free Polygon WebSocket endpoints (no auth needed)
WSS_ENDPOINTS = [
    "wss://polygon-bor-rpc.publicnode.com",
    "wss://polygon.drpc.org",
]

# Polymarket Data API (unauthenticated, free)
DATA_API = "https://data-api.polymarket.com"

# OrderFilled event signature: keccak256 of the Solidity event
# OrderFilled(bytes32 indexed orderHash, address indexed maker, address indexed taker,
#             uint256 makerAssetId, uint256 takerAssetId,
#             uint256 makerAmountFilled, uint256 takerAmountFilled, uint256 fee)
def _keccak256(text):
    """Compute Keccak-256 hash (Ethereum standard, NOT SHA3-256)."""
    try:
        from Crypto.Hash import keccak
        k = keccak.new(digest_bits=256)
        k.update(text.encode())
        return "0x" + k.hexdigest()
    except ImportError:
        # Fallback: use hashlib (Python 3.6+ has sha3, but it's NIST SHA3 not Keccak)
        # This won't match Ethereum — pycryptodome is needed
        return "0x" + hashlib.sha3_256(text.encode()).hexdigest()

ORDER_FILLED_TOPIC = _keccak256(
    "OrderFilled(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)"
)

# All tracked whale addresses (lowercase for comparison)
WHALE_REGISTRY = {
    "0x61276aba49117fd9299707d5d573652949d5c977": "MuseumOfBees",
    "0x970e744a34cd0795ff7b4ba844018f17b7fd5c26": "tugao9",
    "0x2eb5714ff6f20f5f9f7662c556dbef5e1c9bf4d4": "Realistic-Swivel",
    "0x87650b9f63563f7c456d9bbcceee5f9faf06ed81": "2B9S",
    "0xb2a3623364c33561d8312e1edb79eb941c798510": "aekghas",
    "0x96489abcb9f583d6835c8ef95ffc923d05a86825": "anoin123",
    "0x1cc16713196d456f86fa9c7387dd326a7f73b8df": "Wickier",
    "0x7744bfd749a70020d16a1fcbac1d064761c9999e": "chungguskhan",
    "0xde7be6d489bce070a959e0cb813128ae659b5f4b": "wan123",
    "0x4d49acb0ae1c463eb5b1947d174141b812ba7450": "no1yet",
    "0xad142563a8d80e3f6a18ca5fa5936027942bbf69": "myfirstpubes",
}

# Lowercase set for fast lookup
_WHALE_ADDRS = {addr.lower() for addr in WHALE_REGISTRY}


# =====================
# WHALE WATCHER
# =====================

class WhaleWatcher:
    """Monitors whale wallets in real-time using Polygon WebSocket + Data API fallback."""

    def __init__(self):
        self._trades = collections.deque(maxlen=500)
        self._positions_cache = {}    # addr → [positions]
        self._token_map = {}          # token_id → {"title": ..., "outcome": ...}
        self._seen_tx_hashes = set()  # Dedup across both sources
        self._lock = threading.Lock()
        self._running = False
        self._ws_connected = False
        self._ws_events_count = 0
        self._api_events_count = 0
        self._last_api_poll = 0
        self._log_lines = collections.deque(maxlen=50)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] WHALE: {msg}"
        self._log_lines.append(line)
        print(f"  {line}")

    # ---- Public API (thread-safe) ----

    def start(self):
        """Launch both monitoring threads."""
        self._running = True
        # Thread 1: WebSocket listener (async)
        t1 = threading.Thread(target=self._ws_thread, daemon=True, name="whale-ws")
        t1.start()
        # Thread 2: Data API poller
        t2 = threading.Thread(target=self._api_thread, daemon=True, name="whale-api")
        t2.start()
        self.log(f"Started — tracking {len(WHALE_REGISTRY)} whales")

    def stop(self):
        """Signal threads to stop."""
        self._running = False
        self.log("Stopped")

    def get_recent_trades(self, max_age=300):
        """Return whale trades from the last N seconds (thread-safe)."""
        cutoff = time.time() - max_age
        with self._lock:
            return [t for t in self._trades if t["timestamp"] >= cutoff]

    def get_crypto_trades(self, up_token=None, down_token=None, max_age=300):
        """Return whale trades matching specific token IDs (for arena crypto matching)."""
        cutoff = time.time() - max_age
        results = []
        token_set = set()
        if up_token:
            token_set.add(str(up_token))
        if down_token:
            token_set.add(str(down_token))

        with self._lock:
            for t in self._trades:
                if t["timestamp"] < cutoff:
                    continue
                # Match by token_id (on-chain) or by title pattern (Data API)
                if t.get("token_id") and str(t["token_id"]) in token_set:
                    results.append(t)
                elif t.get("is_crypto_updown"):
                    results.append(t)
        return results

    def get_positions(self, address):
        """Return cached positions for a whale (from Data API)."""
        with self._lock:
            return self._positions_cache.get(address.lower(), [])

    def get_status(self):
        """Return watcher status for dashboard."""
        return {
            "running": self._running,
            "ws_connected": self._ws_connected,
            "ws_events": self._ws_events_count,
            "api_events": self._api_events_count,
            "total_trades": len(self._trades),
            "log": list(self._log_lines),
        }

    # ---- Thread 1: Polygon WebSocket ----

    def _ws_thread(self):
        """Run the async WebSocket listener in its own event loop."""
        while self._running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._ws_listen())
            except Exception as e:
                self.log(f"WebSocket error: {e}")
                self._ws_connected = False
            if self._running:
                self.log("WebSocket reconnecting in 5s...")
                time.sleep(5)

    async def _ws_listen(self):
        """Subscribe to OrderFilled events on CTF Exchange via WebSocket."""
        try:
            import websockets
        except ImportError:
            self.log("websockets library not installed — WebSocket disabled")
            self._ws_connected = False
            return

        for endpoint in WSS_ENDPOINTS:
            try:
                self.log(f"Connecting to {endpoint}...")
                async with websockets.connect(endpoint, ping_interval=30, ping_timeout=10) as ws:
                    # Subscribe to OrderFilled logs on CTF Exchange
                    sub_msg = json.dumps({
                        "jsonrpc": "2.0",
                        "method": "eth_subscribe",
                        "params": ["logs", {
                            "address": CTF_EXCHANGE,
                            "topics": [ORDER_FILLED_TOPIC],
                        }],
                        "id": 1,
                    })
                    await ws.send(sub_msg)

                    # Read subscription response
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                    if "result" in resp:
                        sub_id = resp["result"]
                        self._ws_connected = True
                        self.log(f"WebSocket subscribed (id={sub_id[:12]}...)")
                    else:
                        error = resp.get("error", {}).get("message", "unknown")
                        self.log(f"WebSocket subscribe failed: {error}")
                        continue

                    # Listen for events
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=30)
                            msg = json.loads(raw)

                            if msg.get("method") == "eth_subscription":
                                log_data = msg.get("params", {}).get("result", {})
                                self._handle_ws_event(log_data)

                        except asyncio.TimeoutError:
                            # No events for 30s — send ping to keep alive
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            self.log("WebSocket connection closed")
                            self._ws_connected = False
                            break

                    self._ws_connected = False
                    return  # Will reconnect in outer loop

            except Exception as e:
                self.log(f"WebSocket {endpoint} failed: {e}")
                continue

        # All endpoints failed
        self._ws_connected = False
        self.log("All WebSocket endpoints failed — falling back to API only")

    def _handle_ws_event(self, log_data):
        """Decode an OrderFilled event and check if it involves a whale."""
        topics = log_data.get("topics", [])
        data = log_data.get("data", "")
        tx_hash = log_data.get("transactionHash", "")

        if len(topics) < 4:
            return

        # Extract maker and taker addresses from indexed topics
        maker = "0x" + topics[2][-40:]
        taker = "0x" + topics[3][-40:]
        maker_lower = maker.lower()
        taker_lower = taker.lower()

        # Check if either is a whale
        whale_addr = None
        whale_role = None
        if maker_lower in _WHALE_ADDRS:
            whale_addr = maker_lower
            whale_role = "maker"
        elif taker_lower in _WHALE_ADDRS:
            whale_addr = taker_lower
            whale_role = "taker"
        else:
            return  # Not a whale trade

        # Dedup
        if tx_hash in self._seen_tx_hashes:
            return
        self._seen_tx_hashes.add(tx_hash)
        if len(self._seen_tx_hashes) > 5000:
            # Trim old hashes
            self._seen_tx_hashes = set(list(self._seen_tx_hashes)[-2000:])

        # Decode data field: 5 x uint256 (each 32 bytes = 64 hex chars)
        data_hex = data[2:] if data.startswith("0x") else data
        if len(data_hex) < 320:  # Need at least 5 * 64 = 320 hex chars
            return

        chunks = [data_hex[i:i+64] for i in range(0, 320, 64)]
        maker_asset_id = int(chunks[0], 16)
        taker_asset_id = int(chunks[1], 16)
        maker_amount = int(chunks[2], 16) / 1e6  # USDC has 6 decimals
        taker_amount = int(chunks[3], 16) / 1e6
        fee = int(chunks[4], 16) / 1e6

        # Determine side: assetId == 0 means USDC (collateral)
        # If whale is maker and makerAssetId == 0 → whale pays USDC → BUY
        # If whale is taker and takerAssetId == 0 → whale pays USDC → BUY
        if whale_role == "maker":
            if maker_asset_id == 0:
                side = "BUY"
                token_id = str(taker_asset_id)
                usdc_amount = maker_amount
                shares = taker_amount
            else:
                side = "SELL"
                token_id = str(maker_asset_id)
                usdc_amount = taker_amount
                shares = maker_amount
        else:  # taker
            if taker_asset_id == 0:
                side = "BUY"
                token_id = str(maker_asset_id)
                usdc_amount = taker_amount
                shares = maker_amount
            else:
                side = "SELL"
                token_id = str(taker_asset_id)
                usdc_amount = maker_amount
                shares = taker_amount

        price = usdc_amount / shares if shares > 0 else 0

        whale_name = WHALE_REGISTRY.get(whale_addr, whale_addr[:10])

        trade = {
            "source": "websocket",
            "timestamp": time.time(),
            "whale_addr": whale_addr,
            "whale_name": whale_name,
            "side": side,
            "token_id": token_id,
            "usdc_amount": round(usdc_amount, 2),
            "shares": round(shares, 2),
            "price": round(price, 4),
            "fee": round(fee, 4),
            "tx_hash": tx_hash,
            "title": "",       # Enriched later by API poller
            "outcome": "",     # Enriched later by API poller
            "is_crypto_updown": False,  # Enriched later
        }

        # Try to enrich from token map
        with self._lock:
            if token_id in self._token_map:
                mapping = self._token_map[token_id]
                trade["title"] = mapping.get("title", "")
                trade["outcome"] = mapping.get("outcome", "")
                trade["is_crypto_updown"] = "up or down" in trade["title"].lower()

            self._trades.append(trade)
            self._ws_events_count += 1

        self.log(f"WS {whale_name}: {side} {shares:.1f} @ ${price:.3f} (${usdc_amount:.2f})")

    # ---- Thread 2: Data API Poller ----

    def _api_thread(self):
        """Poll Polymarket Data API for whale activity every 5 seconds."""
        while self._running:
            try:
                self._poll_all_whales()
            except Exception as e:
                self.log(f"API poll error: {e}")
            time.sleep(5)

    def _poll_all_whales(self):
        """Fetch recent activity for all whales in parallel."""

        def fetch_one(addr):
            try:
                resp = requests.get(
                    f"{DATA_API}/activity",
                    params={"user": addr, "limit": 10},
                    timeout=8,
                )
                if resp.status_code == 200:
                    return addr, resp.json()
            except Exception:
                pass
            return addr, []

        # Parallel fetch all whales
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(fetch_one, WHALE_REGISTRY.keys()))

        now = time.time()

        for addr, activities in results:
            if not isinstance(activities, list):
                continue

            for trade in activities:
                if trade.get("type") != "TRADE":
                    continue

                tx_hash = trade.get("transactionHash", "")
                if not tx_hash:
                    continue

                # Dedup with WebSocket events
                if tx_hash in self._seen_tx_hashes:
                    continue

                # Check recency (only trades from last 5 minutes)
                trade_ts = trade.get("timestamp", 0)
                if isinstance(trade_ts, str):
                    try:
                        trade_ts = int(trade_ts)
                    except ValueError:
                        continue
                age = now - trade_ts
                if age > 300:
                    continue

                self._seen_tx_hashes.add(tx_hash)

                title = trade.get("title") or ""
                outcome = trade.get("outcome") or ""
                side_raw = trade.get("side", "")
                usdc = float(trade.get("usdcSize") or 0)
                shares = float(trade.get("size") or 0)
                price = float(trade.get("price") or 0)
                asset = trade.get("asset", "")

                if usdc <= 0:
                    usdc = shares * price

                is_crypto = "up or down" in title.lower()
                whale_name = WHALE_REGISTRY.get(addr.lower(), addr[:10])

                # Determine crypto side from outcome
                crypto_side = ""
                if is_crypto:
                    outcome_lower = outcome.lower()
                    if "up" in outcome_lower:
                        crypto_side = "UP"
                    elif "down" in outcome_lower:
                        crypto_side = "DOWN"

                entry = {
                    "source": "api",
                    "timestamp": trade_ts,
                    "whale_addr": addr.lower(),
                    "whale_name": whale_name,
                    "side": side_raw,
                    "token_id": asset,
                    "usdc_amount": round(usdc, 2),
                    "shares": round(shares, 2),
                    "price": round(price, 4),
                    "fee": 0,
                    "tx_hash": tx_hash,
                    "title": title,
                    "outcome": outcome,
                    "is_crypto_updown": is_crypto,
                    "crypto_side": crypto_side,
                }

                # Update token map for future WebSocket enrichment
                if asset and title:
                    self._token_map[str(asset)] = {
                        "title": title,
                        "outcome": outcome,
                    }

                with self._lock:
                    self._trades.append(entry)
                    self._api_events_count += 1

                self.log(f"API {whale_name}: {side_raw} {outcome} on {title[:45]} ${usdc:.2f}")

    def _poll_positions(self):
        """Fetch open positions for all whales (for dashboard)."""

        def fetch_pos(addr):
            try:
                resp = requests.get(
                    f"{DATA_API}/positions",
                    params={"user": addr, "limit": 20},
                    timeout=8,
                )
                if resp.status_code == 200:
                    return addr, resp.json()
            except Exception:
                pass
            return addr, []

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(fetch_pos, WHALE_REGISTRY.keys()))

        with self._lock:
            for addr, positions in results:
                if isinstance(positions, list):
                    self._positions_cache[addr.lower()] = positions

    # ---- State for Dashboard ----

    def write_state(self, filepath):
        """Write watcher state to JSON file for dashboard to read."""
        status = self.get_status()
        recent = self.get_recent_trades(max_age=600)

        state = {
            "status": status,
            "recent_trades": recent[-50:],  # Last 50
            "whale_names": dict(WHALE_REGISTRY),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            import tempfile, os
            dir_name = os.path.dirname(filepath) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp_path, filepath)
        except Exception:
            pass


# =====================
# CLI TEST
# =====================

if __name__ == "__main__":
    import sys

    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"Testing WhaleWatcher for {duration} seconds...")
    print(f"Tracking {len(WHALE_REGISTRY)} whales")
    print(f"OrderFilled topic: {ORDER_FILLED_TOPIC}")
    print()

    watcher = WhaleWatcher()
    watcher.start()

    try:
        start = time.time()
        while time.time() - start < duration:
            time.sleep(10)
            status = watcher.get_status()
            trades = watcher.get_recent_trades(max_age=300)
            print(f"\n--- Status at {int(time.time()-start)}s ---")
            print(f"  WS connected: {status['ws_connected']}")
            print(f"  WS events: {status['ws_events']}")
            print(f"  API events: {status['api_events']}")
            print(f"  Total trades (5min): {len(trades)}")
            for t in trades[-3:]:
                print(f"    {t['whale_name']}: {t['side']} {t.get('outcome','')} ${t['usdc_amount']:.2f} ({t['source']})")
    except KeyboardInterrupt:
        pass

    watcher.stop()
    print("\nDone!")
