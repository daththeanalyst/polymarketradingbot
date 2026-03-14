"""
Strategy Arena — Multi-Strategy Paper Trading Competition
==========================================================
Runs 9 strategies in parallel, each starting with $100.
Logs all trades to CSV, writes state to JSON for the dashboard.

Strategies:
  CRYPTO (5-min BTC/ETH markets):
    1. Current   — 3% edge, flat $5, TP/SL exits
    2. Kelly     — Kelly criterion bet sizing
    3. Aggressive — Last 60s, 1% edge, rides to resolution
    4. MicroArb  — Buy YES+NO when gap > 3c (structural arb on 5-min)
    5. Momentum  — Pure BTC momentum, no edge calc
    6. MeanRevert — Contrarian: bet against extreme odds (>70c)

  GENERAL (all Polymarket markets):
    7. HighProb  — Buy YES at 92-97c on near-certainties
    8. Longshot  — Sub-5c bets in underpriced categories
    9. Random    — Coin flip baseline (control group)
   10. WhaleMirror — Copy trades from top trader

Usage:
  python arena.py                    # Run 12 hours (default)
  python arena.py --duration 60      # Run 60 minutes
  python arena.py --duration 720     # Run 12 hours
"""

import os
import csv
import time
import json
import random
import hashlib
import tempfile
import requests
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

from config import (
    GAMMA_API, CLOB_API, BINANCE_API, POLYMARKET_FEE_RATE,
    SCALP_POLL_INTERVAL, SCALP_PAPER_SLIPPAGE, SCALP_PAPER_FEE,
    SCALP_MIN_EDGE, SCALP_BET_SIZE, SCALP_PROFIT_TARGET,
    SCALP_STOP_LOSS, SCALP_HEDGE_THRESHOLD,
    SCALP_KELLY_FRACTION, SCALP_KELLY_MIN_EDGE,
    SCALP_KELLY_MAX_BET, SCALP_KELLY_MIN_BET,
    SCALP_AGGRESSIVE_MIN_EDGE, SCALP_AGGRESSIVE_BET_SIZE,
    SCALP_AGGRESSIVE_MAX_TIME, SCALP_AGGRESSIVE_MOMENTUM_ONLY,
    CATEGORY_SCORES, CATEGORY_KEYWORDS,
)
from math_utils import kelly_fraction as calc_kelly, position_size as calc_position_size
from whale_watcher import WhaleWatcher

# =====================
# CONSTANTS
# =====================

ARENA_DIR = os.path.dirname(os.path.abspath(__file__))
ARENA_STATE_FILE = os.path.join(ARENA_DIR, "arena_state.json")
ARENA_STOP_FILE = ARENA_STATE_FILE + ".stop"
ARENA_TRADE_LOG = os.path.join(ARENA_DIR, "arena_trades.csv")
STARTING_BALANCE = 100.00

TRADE_LOG_FIELDS = [
    "timestamp", "session_id", "strategy", "market_type",
    "market_id", "title", "side", "entry_price", "shares",
    "cost", "edge", "exit_price", "exit_type", "pnl", "pnl_pct",
    "hold_duration_s", "winner", "we_won",
]

_SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

# Binance symbols
BINANCE_SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT"}

# Slug patterns for crypto up/down markets
COIN_SLUG_PATTERNS = {
    "btc": {"5min": ("btc-updown-5m-{}", 300), "15min": ("btc-updown-15m-{}", 900)},
    "eth": {"5min": ("eth-updown-5m-{}", 300), "15min": ("eth-updown-15m-{}", 900)},
}


# =====================
# TRADE LOGGING
# =====================

def _log_arena_trade(row):
    """Append a completed trade to the arena CSV log."""
    file_exists = os.path.exists(ARENA_TRADE_LOG)
    try:
        with open(ARENA_TRADE_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print(f"  [WARN] Failed to log arena trade: {e}")


def load_arena_trades():
    """Load all arena trades from CSV."""
    if not os.path.exists(ARENA_TRADE_LOG):
        return []
    try:
        with open(ARENA_TRADE_LOG, "r") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


# =====================
# DATA FEEDS
# =====================

def get_crypto_price(coin="btc"):
    """Fetch current crypto spot price from Binance."""
    symbol = BINANCE_SYMBOLS.get(coin.lower(), f"{coin.upper()}USDT")
    try:
        resp = requests.get(f"{BINANCE_API}/ticker/price", params={"symbol": symbol}, timeout=3)
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception:
        return None


def get_crypto_prices_bulk(coin="btc", minutes=2):
    """Fetch recent crypto prices for momentum."""
    symbol = BINANCE_SYMBOLS.get(coin.lower(), f"{coin.upper()}USDT")
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": minutes + 1},
            timeout=3,
        )
        resp.raise_for_status()
        return [float(k[4]) for k in resp.json()]
    except Exception:
        return []


def get_clob_midpoint(token_id):
    """Fetch real-time midpoint price from CLOB API."""
    try:
        resp = requests.get(f"{CLOB_API}/midpoint", params={"token_id": token_id}, timeout=3)
        resp.raise_for_status()
        return float(resp.json().get("mid", 0))
    except Exception:
        return None


def get_clob_book(token_id):
    """Fetch full order book from CLOB API.

    Returns dict with 'best_bid', 'best_ask', 'bids' (desc), 'asks' (asc),
    or None on failure.
    """
    try:
        resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        raw_bids = data.get("bids", [])
        raw_asks = data.get("asks", [])
        # API returns bids ascending (worst→best), asks descending (worst→best)
        # Normalize: bids descending (best first), asks ascending (best first)
        bids = [{"price": float(b["price"]), "size": float(b["size"])} for b in reversed(raw_bids)]
        asks = [{"price": float(a["price"]), "size": float(a["size"])} for a in reversed(raw_asks)]
        return {
            "best_bid": bids[0]["price"] if bids else 0,
            "best_ask": asks[0]["price"] if asks else 0,
            "bids": bids,  # Best (highest) first
            "asks": asks,  # Best (lowest) first
        }
    except Exception:
        return None


def walk_book(levels, amount_usd):
    """Walk order book levels to fill an order of given USD size.

    Args:
        levels: list of {"price": float, "size": float} sorted best-first
        amount_usd: how much USD to spend

    Returns: (avg_fill_price, total_shares, total_cost) or (0, 0, 0) if unfillable
    """
    filled_shares = 0
    total_cost = 0
    remaining = amount_usd

    for level in levels:
        if remaining <= 0:
            break
        price = level["price"]
        available_shares = level["size"]
        max_shares_at_level = remaining / price if price > 0 else 0
        fill_shares = min(available_shares, max_shares_at_level)
        cost = fill_shares * price
        filled_shares += fill_shares
        total_cost += cost
        remaining -= cost

    if filled_shares <= 0:
        return 0, 0, 0
    avg_price = total_cost / filled_shares
    return avg_price, filled_shares, total_cost


def fetch_gamma_event(slug):
    """Fetch event from Gamma API. Returns (event, market) or None."""
    try:
        resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug}, timeout=5)
        resp.raise_for_status()
        events = resp.json()
        if not events:
            return None
        event = events[0]
        markets = event.get("markets", [])
        if not markets:
            return None
        return (event, markets[0])
    except Exception:
        return None


def fetch_crypto_market(coin="btc", market_type="5min"):
    """Fetch current crypto up/down market with FULL order book data.

    Returns realistic bid/ask prices from the actual CLOB order book,
    not just the midpoint. This enables realistic trade simulation.
    """
    patterns = COIN_SLUG_PATTERNS.get(coin, COIN_SLUG_PATTERNS["btc"])
    pattern, interval = patterns.get(market_type, patterns["5min"])
    now = int(time.time())
    window_ts = (now // interval) * interval
    slug = pattern.format(window_ts)

    # Parallel fetch: crypto price + market data
    with ThreadPoolExecutor(max_workers=2) as pool:
        price_future = pool.submit(get_crypto_price, coin)
        gamma_future = pool.submit(fetch_gamma_event, slug)
        crypto_price = price_future.result()
        gamma_result = gamma_future.result()

    if not gamma_result:
        return crypto_price, None

    event, market = gamma_result
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
        gamma_prices = json.loads(market.get("outcomePrices", "[]"))
    except (json.JSONDecodeError, TypeError):
        return crypto_price, None

    if len(outcomes) < 2 or len(token_ids) < 2 or len(gamma_prices) < 2:
        return crypto_price, None

    # Parallel fetch: FULL order books for both tokens
    with ThreadPoolExecutor(max_workers=2) as pool:
        up_f = pool.submit(get_clob_book, token_ids[0])
        down_f = pool.submit(get_clob_book, token_ids[1])
        up_book = up_f.result()
        down_book = down_f.result()

    # Extract real bid/ask prices from order books
    fallback_up = float(gamma_prices[0])
    fallback_down = float(gamma_prices[1])

    if up_book and up_book["best_ask"] > 0:
        up_ask = up_book["best_ask"]    # Price to BUY UP tokens
        up_bid = up_book["best_bid"]    # Price to SELL UP tokens
        up_mid = (up_ask + up_bid) / 2  # Midpoint for display
    else:
        up_ask = up_bid = up_mid = fallback_up
        up_book = None

    if down_book and down_book["best_ask"] > 0:
        down_ask = down_book["best_ask"]
        down_bid = down_book["best_bid"]
        down_mid = (down_ask + down_bid) / 2
    else:
        down_ask = down_bid = down_mid = fallback_down
        down_book = None

    return crypto_price, {
        "id": market.get("id", ""),
        "title": event.get("title", ""),
        "slug": slug,
        # Display price (midpoint, for strategy signal detection)
        "up_price": up_mid,
        "down_price": down_mid,
        # REALISTIC: actual bid/ask from order book
        "up_ask": up_ask,      # What you PAY to buy UP
        "up_bid": up_bid,      # What you GET selling UP
        "down_ask": down_ask,  # What you PAY to buy DOWN
        "down_bid": down_bid,  # What you GET selling DOWN
        # Full order books for walk-the-book fills
        "up_book": up_book,
        "down_book": down_book,
        "up_token": token_ids[0],
        "down_token": token_ids[1],
        "volume": float(event.get("volume", 0) or 0),
        "accepting_orders": market.get("acceptingOrders", False),
        "window_end": window_ts + interval,
    }


def fetch_general_markets(limit=100):
    """Fetch active markets from Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"limit": limit, "active": "true", "closed": "false"},
            timeout=15,
        )
        resp.raise_for_status()
        markets = resp.json()
        # Parse JSON string fields
        for m in markets:
            for field in ("outcomePrices", "outcomes", "clobTokenIds"):
                val = m.get(field)
                if isinstance(val, str):
                    try:
                        m[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
        return markets
    except Exception:
        return []


def get_market_time_remaining(market):
    """Seconds remaining until market resolves."""
    window_end = market.get("window_end")
    if window_end:
        return max(0, window_end - time.time())
    return 300


def check_market_resolution(slug, max_wait=60):
    """Poll for market resolution. Returns 'Up', 'Down', or None."""
    for _ in range(max_wait // 5):
        try:
            resp = requests.get(f"{GAMMA_API}/events", params={"slug": slug}, timeout=10)
            resp.raise_for_status()
            events = resp.json()
            if not events:
                time.sleep(5)
                continue
            event = events[0]
            market = event.get("markets", [{}])[0]
            is_closed = event.get("closed", False) or market.get("closed", False)
            prices = json.loads(market.get("outcomePrices", "[]"))
            if len(prices) >= 2:
                up_price = float(prices[0])
                down_price = float(prices[1])
                if up_price > 0.85:
                    return "Up"
                elif down_price > 0.85:
                    return "Down"
                if is_closed:
                    return "Up" if up_price > down_price else "Down"
        except Exception:
            pass
        time.sleep(5)
    return None


# =====================
# POSITION & STRATEGY BASE
# =====================

@dataclass
class Position:
    """A single open position."""
    side: str                   # "UP", "DOWN", "YES", "NO"
    entry_price: float
    shares: float
    cost: float
    market_id: str
    title: str
    slug: str = ""
    window_end: float = 0
    entry_time: float = field(default_factory=time.time)
    extra: Dict = field(default_factory=dict)

    def pnl(self, current_price):
        return self.shares * current_price - self.cost

    def pnl_pct(self, current_price):
        return self.pnl(current_price) / self.cost if self.cost > 0 else 0


class Strategy(ABC):
    """Abstract base for all arena strategies."""

    def __init__(self, name: str, display_name: str, category: str = "crypto"):
        self.name = name
        self.display_name = display_name
        self.category = category  # "crypto" or "general"
        self.balance = STARTING_BALANCE
        self.position: Optional[Position] = None
        self.trades: List[Dict] = []
        self._log_lines: List[str] = []

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{self.display_name}] {msg}"
        print(f"  {line}")
        self._log_lines.append(line)
        if len(self._log_lines) > 30:
            self._log_lines = self._log_lines[-30:]

    def enter(self, side, price, bet_size, market_id, title, slug="", window_end=0, extra=None, market=None):
        """Open a position with realistic order book execution.

        Uses the actual ask side of the CLOB order book to determine fill price.
        If no order book is available, falls back to displayed price + 1c spread.
        """
        if price <= 0 or price >= 1.0:
            return False

        # Determine the REAL fill price by walking the order book
        book = None
        if market:
            if side == "UP":
                book = market.get("up_book")
            elif side == "DOWN":
                book = market.get("down_book")

        if book and book.get("asks"):
            # REALISTIC: walk the ask side of the order book
            avg_fill, shares, cost = walk_book(book["asks"], bet_size)
            if avg_fill <= 0 or shares < 5:
                return False
            cost = round(cost, 4)
            shares = round(shares, 2)
        else:
            # Fallback: use ask price if available, otherwise price + 1 tick
            if market:
                ask_price = market.get(f"{side.lower()}_ask", price + 0.01)
            else:
                ask_price = price + 0.01
            ask_price = min(ask_price, 0.99)
            if ask_price <= 0:
                return False
            shares = round(bet_size / ask_price, 2)
            if shares < 5:
                return False
            cost = round(shares * ask_price, 4)
            avg_fill = ask_price

        # Strict balance check — never go negative
        if self.balance < cost:
            self.log(f"SKIP: insufficient balance ${self.balance:.2f} < ${cost:.2f}")
            return False

        self.balance = round(self.balance - cost, 4)
        self.position = Position(
            side=side, entry_price=round(avg_fill, 4), shares=shares, cost=cost,
            market_id=market_id, title=title, slug=slug,
            window_end=window_end, extra=extra or {},
        )
        self.log(f"ENTER {side} {shares:.1f}sh @ ${avg_fill:.3f} | Cost ${cost:.2f} | Bal ${self.balance:.2f}")
        return True

    def exit_trade(self, exit_price, exit_type, pnl, winner=None, we_won=None):
        """Close position, credit balance, log trade."""
        if not self.position:
            return
        pos = self.position
        hold_s = time.time() - pos.entry_time
        pnl_pct = round(pnl / pos.cost, 4) if pos.cost > 0 else 0

        trade = {
            "strategy": self.name,
            "side": pos.side,
            "entry_price": round(pos.entry_price, 4),
            "exit_price": round(exit_price, 4),
            "shares": round(pos.shares, 2),
            "cost": round(pos.cost, 4),
            "pnl": round(pnl, 4),
            "exit_type": exit_type,
            "title": pos.title,
            "winner": winner or "",
            "we_won": we_won if we_won is not None else "",
        }
        self.trades.append(trade)

        # Credit proceeds (strict: cost back + profit, or cost - loss)
        proceeds = pos.cost + pnl
        self.balance = round(self.balance + max(0, proceeds), 4)

        self.log(f"EXIT {exit_type}: P&L ${pnl:+.2f} | Bal ${self.balance:.2f}")

        # Log to CSV
        _log_arena_trade({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": _SESSION_ID,
            "strategy": self.name,
            "market_type": self.category,
            "market_id": pos.market_id,
            "title": (pos.title or "")[:100],
            "side": pos.side,
            "entry_price": round(pos.entry_price, 4),
            "shares": round(pos.shares, 2),
            "cost": round(pos.cost, 4),
            "edge": pos.extra.get("edge", ""),
            "exit_price": round(exit_price, 4),
            "exit_type": exit_type,
            "pnl": round(pnl, 4),
            "pnl_pct": pnl_pct,
            "hold_duration_s": round(hold_s, 1),
            "winner": winner or "",
            "we_won": we_won if we_won is not None else "",
        })

        self.position = None

    def summary(self):
        if not self.trades:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "total_pnl": 0, "win_rate": 0, "roi": 0,
                "balance": round(self.balance, 2),
            }
        total_pnl = sum(t["pnl"] for t in self.trades)
        total_cost = sum(t["cost"] for t in self.trades)
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return {
            "total_trades": len(self.trades),
            "wins": wins,
            "losses": len(self.trades) - wins,
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(wins / len(self.trades), 4),
            "roi": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "balance": round(self.balance, 2),
        }

    @abstractmethod
    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        """Called every 2 seconds with crypto market data. Only for crypto strategies."""
        pass

    @abstractmethod
    def on_market_resolve(self, winner):
        """Called when the current 5-min market resolves."""
        pass

    def on_general_tick(self, all_markets):
        """Called every 5 min with general market data. Override for general strategies."""
        pass


# =====================
# CRYPTO STRATEGIES (1-6)
# =====================

class CurrentStrategy(Strategy):
    """Strategy 1: Standard scalper — 3% edge, $5 flat, TP/SL."""

    def __init__(self):
        super().__init__("current", "Current", "crypto")
        self.min_edge = SCALP_MIN_EDGE
        self.bet_size = SCALP_BET_SIZE
        self.profit_target = SCALP_PROFIT_TARGET
        self.stop_loss = SCALP_STOP_LOSS

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            self._check_exit(market, time_remaining)
            return

        # Don't enter in last 60s (that's Aggressive's territory)
        if time_remaining < 60:
            return

        signal = self._detect_signal(prices_history, market)
        if signal:
            side, edge, fair = signal
            token_price = market["up_price"] if side == "UP" else market["down_price"]
            self.enter(
                side, token_price, self.bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"edge": edge, "fair": fair}, market=market,
            )

    def _detect_signal(self, prices, market):
        if len(prices) < 2:
            return None
        momentum = (prices[-1] - prices[0]) / prices[0]
        fair_up = max(0.10, min(0.90, 0.50 + momentum * 50))
        fair_down = 1.0 - fair_up
        up_edge = fair_up - market["up_price"]
        if up_edge > self.min_edge:
            return ("UP", round(up_edge, 4), round(fair_up, 4))
        down_edge = fair_down - market["down_price"]
        if down_edge > self.min_edge:
            return ("DOWN", round(down_edge, 4), round(fair_down, 4))
        return None

    def _check_exit(self, market, time_remaining):
        pos = self.position
        current_price = market.get("up_bid", market["up_price"]) if pos.side == "UP" else market.get("down_bid", market["down_price"])
        pnl_pct = pos.pnl_pct(current_price)

        if pnl_pct >= self.profit_target:
            sell_price = current_price  # Already using real bid price from order book
            pnl = pos.pnl(sell_price)
            self.exit_trade(sell_price, "profit_target", pnl)
        elif pnl_pct < -self.stop_loss:
            sell_price = current_price  # Already using real bid price from order book
            pnl = pos.pnl(sell_price)
            self.exit_trade(sell_price, "stop_loss", pnl)
        elif time_remaining < 30 and pnl_pct < -0.10:
            sell_price = current_price  # Already using real bid price from order book
            pnl = pos.pnl(sell_price)
            self.exit_trade(sell_price, "time_cutoff", pnl)

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            payout = pos.shares * 1.0
            winnings = payout - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class KellyStrategy(Strategy):
    """Strategy 2: Kelly criterion bet sizing."""

    def __init__(self):
        super().__init__("kelly", "Kelly", "crypto")
        self.min_edge = SCALP_KELLY_MIN_EDGE
        self.kelly_fraction = SCALP_KELLY_FRACTION
        self.max_bet = SCALP_KELLY_MAX_BET
        self.min_bet = SCALP_KELLY_MIN_BET

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            self._check_exit(market, time_remaining)
            return

        if time_remaining < 60:
            return

        signal = self._detect_signal(prices_history, market)
        if signal:
            side, edge, fair, bet_size = signal
            token_price = market["up_price"] if side == "UP" else market["down_price"]
            self.enter(
                side, token_price, bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"edge": edge, "fair": fair}, market=market,
            )

    def _detect_signal(self, prices, market):
        if len(prices) < 2:
            return None
        momentum = (prices[-1] - prices[0]) / prices[0]
        fair_up = max(0.10, min(0.90, 0.50 + momentum * 50))
        fair_down = 1.0 - fair_up

        for side, fair, market_price in [
            ("UP", fair_up, market["up_price"]),
            ("DOWN", fair_down, market["down_price"]),
        ]:
            edge = fair - market_price
            if edge > self.min_edge:
                kelly_f = calc_kelly(fair, market_price, fee_rate=0.02)
                if kelly_f <= 0:
                    continue
                bet_size = calc_position_size(
                    fair, market_price, bankroll=self.balance,
                    fraction=self.kelly_fraction, fee_rate=0.02,
                    max_pct=self.max_bet / self.balance if self.balance > 0 else 0.1,
                )
                bet_size = max(self.min_bet, min(bet_size, self.max_bet))
                return (side, round(edge, 4), round(fair, 4), bet_size)
        return None

    def _check_exit(self, market, time_remaining):
        pos = self.position
        current_price = market.get("up_bid", market["up_price"]) if pos.side == "UP" else market.get("down_bid", market["down_price"])
        pnl_pct = pos.pnl_pct(current_price)

        if pnl_pct >= SCALP_PROFIT_TARGET:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "profit_target", pos.pnl(sell_price))
        elif pnl_pct < -SCALP_STOP_LOSS:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "stop_loss", pos.pnl(sell_price))
        elif time_remaining < 30 and pnl_pct < -0.10:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "time_cutoff", pos.pnl(sell_price))

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class AggressiveStrategy(Strategy):
    """Strategy 3: Last-second entry, 1% edge, rides to resolution."""

    def __init__(self):
        super().__init__("aggressive", "Aggressive", "crypto")
        self.min_edge = SCALP_AGGRESSIVE_MIN_EDGE
        self.bet_size = SCALP_AGGRESSIVE_BET_SIZE
        self.max_entry_time = SCALP_AGGRESSIVE_MAX_TIME

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            return  # Ride to resolution, no early exit

        # Only enter in last N seconds
        if time_remaining > self.max_entry_time or time_remaining < 5:
            return

        signal = self._detect_signal(prices_history, market, time_remaining)
        if signal:
            side, edge, fair = signal
            token_price = market["up_price"] if side == "UP" else market["down_price"]
            self.enter(
                side, token_price, self.bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"edge": edge, "fair": fair}, market=market,
            )

    def _detect_signal(self, prices, market, time_remaining):
        if len(prices) < 2:
            return None
        momentum = (prices[-1] - prices[0]) / prices[0]
        fair_up = max(0.10, min(0.90, 0.50 + momentum * 50))
        fair_down = 1.0 - fair_up

        # Standard signal
        up_edge = fair_up - market["up_price"]
        if up_edge > self.min_edge:
            return ("UP", round(up_edge, 4), round(fair_up, 4))
        down_edge = fair_down - market["down_price"]
        if down_edge > self.min_edge:
            return ("DOWN", round(down_edge, 4), round(fair_down, 4))

        # Momentum-only fallback (strong momentum + last 60s)
        if SCALP_AGGRESSIVE_MOMENTUM_ONLY and len(prices) >= 3:
            recent = prices[-6:] if len(prices) >= 6 else prices
            m = (recent[-1] - recent[0]) / recent[0] if recent[0] > 0 else 0
            if abs(m) > 0.001:
                if m > 0:
                    fair = min(0.90, 0.50 + m * 50)
                    edge = fair - market["up_price"]
                    if edge > 0:
                        return ("UP", round(edge, 4), round(fair, 4))
                else:
                    fair = min(0.90, 0.50 + abs(m) * 50)
                    edge = fair - market["down_price"]
                    if edge > 0:
                        return ("DOWN", round(edge, 4), round(fair, 4))
        return None

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class MicroArbStrategy(Strategy):
    """Strategy 4: Buy YES+NO when gap > 3c for guaranteed profit.

    Real mechanics: you buy N shares of YES at up_price, and N shares of NO at down_price.
    Total cost = N * (up_price + down_price). One side pays $1/share at resolution.
    Guaranteed payout = N * $1.00. Fee = 2% on the winning side's payout.
    Net profit = N * (1.0 - fee_rate) - N * (up + down).
    """

    def __init__(self):
        super().__init__("micro_arb", "MicroArb", "crypto")
        self.min_gap = 0.015  # 1.5c minimum gap (tighter to trigger more often)
        self.bet_size = 5.0

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            return  # Already in a trade, wait for resolution

        if time_remaining < 20:
            return  # Too close to resolution

        up = market["up_price"]
        down = market["down_price"]
        total_per_share = up + down
        gap = 1.0 - total_per_share

        # Pure arb: buy both sides when gap covers fees
        # Use real ask prices from order book
        up_ask = market.get("up_ask", up + 0.01)
        down_ask = market.get("down_ask", down + 0.01)
        if gap >= self.min_gap:
            payout_per_share = 1.0
            fee_per_share = payout_per_share * POLYMARKET_FEE_RATE
            arb_total = up_ask + down_ask
            net_profit_per_share = payout_per_share - fee_per_share - arb_total

            if net_profit_per_share > 0:
                max_spend = min(self.balance * 0.05, self.balance)
                num_shares = int(max_spend / arb_total)
                if num_shares >= 5 and self.balance >= num_shares * arb_total:
                    actual_cost = round(num_shares * arb_total, 4)
                    self.balance = round(self.balance - actual_cost, 4)
                    self.position = Position(
                        side="ARB", entry_price=arb_total, shares=num_shares, cost=actual_cost,
                        market_id=market["id"], title=market["title"], slug=market.get("slug", ""),
                        window_end=market.get("window_end", 0),
                        extra={"gap": gap, "up_price": up_ask, "down_price": down_ask, "edge": gap},
                    )
                    self.log(f"ARB ENTER {num_shares}sh (YES+NO) | Cost ${actual_cost:.2f} | Bal ${self.balance:.2f}")
                    return

        # Value buyer fallback: buy the cheaper side when it's under 0.45
        # (the other side is overpriced, so the cheap side has value)
        cheaper_side = "UP" if up < down else "DOWN"
        cheaper_price = min(up, down)

        if cheaper_price < 0.45 and cheaper_price > 0.01:
            self.enter(
                cheaper_side, cheaper_price, self.bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"edge": round(0.50 - cheaper_price, 3), "mode": "value"}, market=market,
            )

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        if pos.side == "ARB":
            # Arb always wins — one side pays $1 per share
            gross_payout = pos.shares * 1.0
            fee = gross_payout * POLYMARKET_FEE_RATE
            net_payout = gross_payout - fee
            pnl = round(net_payout - pos.cost, 4)
            self.exit_trade(1.0, "resolution", pnl, winner, True)
        else:
            we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
            if we_won:
                winnings = pos.shares * 1.0 - pos.cost
                fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
                pnl = winnings - fee
            else:
                pnl = -pos.cost
            self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class MomentumSurgeStrategy(Strategy):
    """Strategy 5: Pure momentum, no edge calculation."""

    def __init__(self):
        super().__init__("momentum", "Momentum", "crypto")
        self.momentum_threshold = 0.0003  # 0.03% BTC move (~$21 on BTC, triggers frequently)
        self.bet_size = 5.0
        self.profit_target = 0.20  # 20% profit target

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            self._check_exit(market, time_remaining)
            return

        if time_remaining < 30 or len(prices_history) < 3:
            return

        # Check for strong momentum over last 30 seconds
        recent = prices_history[-6:] if len(prices_history) >= 6 else prices_history
        if recent[0] <= 0:
            return
        momentum = (recent[-1] - recent[0]) / recent[0]

        if abs(momentum) < self.momentum_threshold:
            return

        if momentum > 0:
            side = "UP"
            token_price = market["up_price"]
        else:
            side = "DOWN"
            token_price = market["down_price"]

        self.enter(
            side, token_price, self.bet_size,
            market["id"], market["title"], market.get("slug", ""),
            market.get("window_end", 0),
            extra={"momentum": momentum, "edge": abs(momentum)}, market=market,
        )

    def _check_exit(self, market, time_remaining):
        pos = self.position
        current_price = market.get("up_bid", market["up_price"]) if pos.side == "UP" else market.get("down_bid", market["down_price"])
        pnl_pct = pos.pnl_pct(current_price)

        if pnl_pct >= self.profit_target:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "profit_target", pos.pnl(sell_price))

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class MeanReversionStrategy(Strategy):
    """Strategy 6: Contrarian — bet against extreme odds."""

    def __init__(self):
        super().__init__("mean_revert", "MeanRevert", "crypto")
        self.extreme_threshold = 0.70  # Bet against when > 70c
        self.bet_size = 5.0
        self.profit_target = 0.15  # 15% profit target

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            self._check_exit(market, time_remaining)
            return

        if time_remaining < 60:
            return

        up = market["up_price"]
        down = market["down_price"]

        # Bet DOWN if UP price is extreme (overreaction)
        if up > self.extreme_threshold:
            self.enter(
                "DOWN", down, self.bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"trigger": f"UP={up:.2f}>0.70", "edge": up - 0.50}, market=market,
            )
            return

        # Bet UP if DOWN price is extreme
        if down > self.extreme_threshold:
            self.enter(
                "UP", up, self.bet_size,
                market["id"], market["title"], market.get("slug", ""),
                market.get("window_end", 0),
                extra={"trigger": f"DOWN={down:.2f}>0.70", "edge": down - 0.50}, market=market,
            )

    def _check_exit(self, market, time_remaining):
        pos = self.position
        current_price = market.get("up_bid", market["up_price"]) if pos.side == "UP" else market.get("down_bid", market["down_price"])
        pnl_pct = pos.pnl_pct(current_price)

        if pnl_pct >= self.profit_target:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "profit_target", pos.pnl(sell_price))
        elif pnl_pct < -0.30:  # 30% stop loss
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "stop_loss", pos.pnl(sell_price))

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


# =====================
# ADDITIONAL CRYPTO STRATEGIES (7-9)
# =====================

class HighProbStrategy(Strategy):
    """Strategy 7: Buy the dominant side when one side is > 70c in crypto markets.

    The idea: when one side is heavily favored (>70c), the market is confident
    about direction. Bet on the favorite — high win rate, small profit per trade.
    """

    def __init__(self):
        super().__init__("high_prob", "HighProb", "crypto")
        self.min_price = 0.60  # Side must be > 60c to enter
        self.max_price = 0.975  # Leave room for fees
        self.bet_size = 5.0
        self.profit_target = 0.10  # 10% profit target

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            self._check_exit(market, time_remaining)
            return

        if time_remaining < 15:
            return  # Too close to resolution

        up = market["up_price"]
        down = market["down_price"]

        # Buy the dominant side (the one > 60c)
        if up >= self.min_price and up <= self.max_price:
            side, price = "UP", up
        elif down >= self.min_price and down <= self.max_price:
            side, price = "DOWN", down
        else:
            return  # No clear favorite

        edge = price - 0.50  # How far from 50/50
        self.enter(
            side, price, self.bet_size,
            market["id"], market["title"], market.get("slug", ""),
            market.get("window_end", 0),
            extra={"edge": round(edge, 3), "confidence": round(price, 3)}, market=market,
        )

    def _check_exit(self, market, time_remaining):
        pos = self.position
        current_price = market.get("up_bid", market["up_price"]) if pos.side == "UP" else market.get("down_bid", market["down_price"])
        pnl_pct = pos.pnl_pct(current_price)
        if pnl_pct >= self.profit_target:
            sell_price = current_price  # Already using real bid price from order book
            self.exit_trade(sell_price, "profit_target", pos.pnl(sell_price))

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)

class LongshotSniperStrategy(Strategy):
    """Strategy 8: Buy the extreme underdog in BTC 5-min markets.

    When one side is < 10c, the market is saying it's very unlikely.
    But if BTC reverses sharply, the underdog pays 10x-50x.
    Small $1 bets, high loss rate, but occasional massive wins.
    """

    def __init__(self):
        super().__init__("longshot", "Longshot", "crypto")
        self.max_price = 0.40  # Buy the underdog when it's the cheaper side
        self.bet_size = 3.0  # Enough for 5+ shares at typical prices

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            return  # Hold to resolution — longshots ride or die

        if time_remaining < 30:
            return

        up = market["up_price"]
        down = market["down_price"]

        # Buy the cheaper (underdog) side when it's under 10c
        if up <= self.max_price and up > 0.005:
            side, price = "UP", up
            multiplier = round(1.0 / up, 1)
        elif down <= self.max_price and down > 0.005:
            side, price = "DOWN", down
            multiplier = round(1.0 / down, 1)
        else:
            return  # No extreme underdog available

        self.enter(
            side, price, self.bet_size,
            market["id"], market["title"], market.get("slug", ""),
            market.get("window_end", 0),
            extra={"edge": round(0.50 - price, 3), "multiplier": multiplier}, market=market,
        )
        if self.position:
            self.log(f"Longshot: {side} @ {price*100:.1f}c ({multiplier}x potential)")

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class RandomBaselineStrategy(Strategy):
    """Strategy 9: Coin flip baseline — randomly picks UP or DOWN on BTC.

    Control group. Every new 5-min window, flip a coin and bet $1.
    No intelligence, no analysis. If other strategies can't beat this,
    they have no real edge.
    """

    def __init__(self):
        super().__init__("random", "Random", "crypto")
        self.bet_size = 5.0
        self._last_market_slug = None  # Track market windows to bet once per window

    def on_crypto_tick(self, crypto_price, market, prices_history, time_remaining):
        if self.position:
            return  # Hold to resolution

        slug = market.get("slug", "")
        if slug == self._last_market_slug:
            return  # Already bet on this window

        if time_remaining < 30:
            return

        # Coin flip: randomly pick UP or DOWN
        side = random.choice(["UP", "DOWN"])
        price = market["up_price"] if side == "UP" else market["down_price"]

        if price <= 0.005 or price >= 0.995:
            return  # Skip extreme prices

        self._last_market_slug = slug
        self.enter(
            side, price, self.bet_size,
            market["id"], market["title"], market.get("slug", ""),
            market.get("window_end", 0),
            extra={"edge": 0, "reason": "coin_flip"}, market=market,
        )
        if self.position:
            self.log(f"Random coin flip: {side} @ {price*100:.1f}c")

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (pos.side == "UP" and winner == "Up") or (pos.side == "DOWN" and winner == "Down")
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            pnl = winnings - fee
        else:
            pnl = -pos.cost
        self.exit_trade(1.0 if we_won else 0.0, "resolution", pnl, winner, we_won)


class WhaleMirrorStrategy(Strategy):
    """Strategy 10: Copy-trade 11 profitable Polymarket whales in real-time.

    Uses WhaleWatcher (Polygon WebSocket + Data API) for ~2-5 second trade detection.
    Enters when 2+ whales agree on the same side. Bet size scales to 10% of whale average.
    """

    SCALE_FACTOR = 0.10    # Mirror at 10% of whale size
    MIN_BET = 5.0          # Polymarket 5-share minimum
    MAX_BET = 20.0         # Cap per trade

    def __init__(self, whale_watcher=None):
        super().__init__("whale", "WhaleMirror", "crypto")
        self.bet_size = 5.0
        self.max_positions = 1
        self._watcher = whale_watcher
        self._current_window_side = None
        self._current_slug = None

    def set_watcher(self, watcher):
        """Set the WhaleWatcher reference (called by ArenaRunner)."""
        self._watcher = watcher

    def on_crypto_tick(self, crypto_price, market, price_history, time_remaining):
        if self.balance < self.MIN_BET:
            return

        slug = market.get("slug", "")

        # New window — reset
        if slug != self._current_slug:
            self._current_slug = slug
            self._current_window_side = None

        # Don't enter in last 15 seconds or first 30 seconds
        if time_remaining < 15 or time_remaining > 270:
            return

        # If we already have a position, check exits
        if self.position:
            self._check_exit(market)
            return

        if not self._watcher:
            return

        # Get whale trades from watcher (real-time, last 5 minutes)
        whale_trades = self._watcher.get_recent_trades(max_age=300)

        # Filter to crypto up/down trades only
        crypto_trades = [t for t in whale_trades if t.get("is_crypto_updown")]

        if not crypto_trades:
            return

        # Count votes per whale (most recent trade per whale wins)
        whale_votes = {}   # {whale_name: side}
        whale_sizes = {}   # {whale_name: usdc_total}

        for t in crypto_trades:
            name = t.get("whale_name", "")
            side = t.get("crypto_side", "")
            usdc = t.get("usdc_amount", 0)

            if not side or not name:
                continue

            whale_votes[name] = side
            whale_sizes[name] = whale_sizes.get(name, 0) + usdc

        # Count consensus
        up_votes = sum(1 for s in whale_votes.values() if s == "UP")
        down_votes = sum(1 for s in whale_votes.values() if s == "DOWN")

        consensus_side = None
        if up_votes >= 2:
            consensus_side = "UP"
        elif down_votes >= 2:
            consensus_side = "DOWN"

        if not consensus_side:
            return

        # Don't re-enter same side in this window
        if consensus_side == self._current_window_side:
            return
        self._current_window_side = consensus_side

        # Scale bet from whale sizes
        sizes = [whale_sizes.get(n, 0) for n, s in whale_votes.items() if s == consensus_side]
        avg_usdc = sum(sizes) / len(sizes) if sizes else 50.0
        scaled_bet = max(self.MIN_BET, min(self.MAX_BET, avg_usdc * self.SCALE_FACTOR))

        price = market.get(f"{consensus_side.lower()}_price", 0.50)
        voters = [n for n, s in whale_votes.items() if s == consensus_side]
        self.log(f"Whale consensus: {consensus_side} ({', '.join(voters)}) avg=${avg_usdc:.0f} -> ${scaled_bet:.2f}")

        self.enter(
            consensus_side, price, scaled_bet,
            market.get("market_id", slug), market.get("title", slug),
            slug=slug,
            window_end=market.get("end_time", 0),
            extra={"whale_votes": f"{up_votes}U/{down_votes}D", "whale_avg": f"${avg_usdc:.0f}", "edge": 0},
            market=market,
        )

    def _check_exit(self, market):
        pos = self.position
        if not pos:
            return
        current_price = market.get(f"{pos.side.lower()}_bid", market.get(f"{pos.side.lower()}_price", 0.50))
        pnl_pct = pos.pnl_pct(current_price)
        if pnl_pct >= SCALP_PROFIT_TARGET:
            sell_value = pos.shares * current_price
            pnl = sell_value - pos.cost
            fee = pnl * SCALP_PAPER_FEE if pnl > 0 else 0
            self.exit_trade(current_price, "profit_target", pnl - fee, pos.side, True)
        elif pnl_pct <= -SCALP_STOP_LOSS:
            sell_value = pos.shares * current_price
            pnl = sell_value - pos.cost
            self.exit_trade(current_price, "stop_loss", pnl, pos.side, False)

    def on_market_resolve(self, winner):
        if not self.position:
            return
        pos = self.position
        we_won = (winner and pos.side.lower() == winner.lower())
        if we_won:
            winnings = pos.shares * 1.0 - pos.cost
            fee = winnings * SCALP_PAPER_FEE if winnings > 0 else 0
            self.exit_trade(1.0, "resolution", winnings - fee, winner, True)
        else:
            self.exit_trade(0.0, "resolution", -pos.cost, winner or "unknown", False)

    def on_general_tick(self, all_markets):
        pass


# =====================
# ARENA RUNNER
# =====================

class ArenaRunner:
    """Runs all 10 strategies in parallel."""

    def __init__(self, coin="btc"):
        self.coin = coin.lower()
        self.whale_watcher = WhaleWatcher()
        self.strategies: List[Strategy] = [
            CurrentStrategy(),
            KellyStrategy(),
            AggressiveStrategy(),
            MicroArbStrategy(),
            MomentumSurgeStrategy(),
            MeanReversionStrategy(),
            HighProbStrategy(),
            LongshotSniperStrategy(),
            RandomBaselineStrategy(),
            WhaleMirrorStrategy(whale_watcher=self.whale_watcher),
        ]
        self._crypto_prices = []
        self._last_crypto = None
        self._last_market = None
        self._last_slug = None
        self._window_start_price = None  # BTC price at start of each 5-min window
        self._state_hash = None
        self._log_lines = []
        self._general_scan_interval = 300  # 5 min
        self._last_general_scan = 0

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(f"  {line}")
        self._log_lines.append(line)
        if len(self._log_lines) > 100:
            self._log_lines = self._log_lines[-100:]

    def _write_state(self, status="running"):
        """Write current state to JSON for dashboard."""
        strategies_data = {}
        for strat in self.strategies:
            pos_data = None
            if strat.position:
                pos = strat.position
                # Get current price for position value
                current_price = 0.50
                if strat.category == "crypto" and self._last_market:
                    if pos.side == "UP":
                        current_price = self._last_market.get("up_bid", self._last_market["up_price"])
                    elif pos.side == "DOWN":
                        current_price = self._last_market.get("down_bid", self._last_market["down_price"])
                    elif pos.side == "ARB":
                        current_price = pos.entry_price  # Arb value stays stable
                else:
                    current_price = pos.entry_price

                pos_data = {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "shares": pos.shares,
                    "cost": round(pos.cost, 4),
                    "current_pnl": round(pos.pnl(current_price), 4),
                    "current_pnl_pct": round(pos.pnl_pct(current_price), 4),
                    "title": pos.title[:80],
                }

            strategies_data[strat.name] = {
                "display_name": strat.display_name,
                "category": strat.category,
                "position": pos_data,
                "trades": strat.trades[-20:],  # Last 20 trades
                "summary": strat.summary(),
                "log": strat._log_lines[-10:],
            }

        market_data = None
        if self._last_market:
            m = self._last_market
            market_data = {
                "title": m.get("title", ""),
                "slug": m.get("slug", ""),
                "up_price": m.get("up_price", 0),
                "down_price": m.get("down_price", 0),
                "up_bid": m.get("up_bid", 0),
                "up_ask": m.get("up_ask", 0),
                "down_bid": m.get("down_bid", 0),
                "down_ask": m.get("down_ask", 0),
                "time_remaining": round(get_market_time_remaining(m)),
            }

        state = {
            "status": status,
            "pid": os.getpid(),
            "timestamp": datetime.now().isoformat(),
            "session_id": _SESSION_ID,
            "coin": self.coin,
            "crypto_price": self._last_crypto,
            "market": market_data,
            "strategies": strategies_data,
            "log": self._log_lines[-50:],
        }

        # Atomic write
        state_json = json.dumps(state, indent=2, sort_keys=True, default=str)
        state_hash = hashlib.md5(state_json.encode()).hexdigest()
        if state_hash == self._state_hash:
            return
        self._state_hash = state_hash

        try:
            dir_name = os.path.dirname(ARENA_STATE_FILE) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                f.write(state_json)
            os.replace(tmp_path, ARENA_STATE_FILE)
        except Exception:
            pass

    def _check_stop(self):
        return os.path.exists(ARENA_STOP_FILE)

    def run(self, duration_minutes=720):
        """Main loop. Default: 12 hours."""
        self.log(f"ARENA STARTED — {len(self.strategies)} strategies competing")
        self.log(f"Coin: {self.coin.upper()} | Duration: {duration_minutes} min")
        self.log(f"Strategies: {', '.join(s.display_name for s in self.strategies)}")
        self.log(f"Each strategy starts with ${STARTING_BALANCE:.0f}")

        # Start whale watcher (WebSocket + Data API threads)
        self.whale_watcher.start()
        self.log("WhaleWatcher started (WebSocket + Data API)")

        # Seed price history
        history = get_crypto_prices_bulk(self.coin, minutes=2)
        if history:
            self._crypto_prices = history
            self.log(f"{self.coin.upper()} at ${history[-1]:,.2f}")

        end_time = time.time() + (duration_minutes * 60)
        tick_count = 0

        try:
            while time.time() < end_time:
                tick_count += 1

                if self._check_stop():
                    self.log("Stop signal received.")
                    break

                # === CRYPTO TICK (every 2 seconds) ===
                crypto_price, market = fetch_crypto_market(self.coin)
                self._last_crypto = crypto_price

                if crypto_price:
                    self._crypto_prices.append(crypto_price)
                    if len(self._crypto_prices) > 12:
                        self._crypto_prices = self._crypto_prices[-12:]

                if market and market.get("accepting_orders", True):
                    time_remaining = get_market_time_remaining(market)

                    # Check if market changed (new window)
                    new_slug = market.get("slug", "")
                    if self._last_slug and new_slug != self._last_slug:
                        # Previous market ended — determine winner from BTC price
                        self.log(f"Market window ended: {self._last_slug}")
                        winner = None
                        if self._window_start_price and crypto_price:
                            if crypto_price > self._window_start_price:
                                winner = "Up"
                            elif crypto_price < self._window_start_price:
                                winner = "Down"
                            else:
                                winner = "Up"  # Tie goes to Up (no change = Up wins on Polymarket)
                            self.log(f"Winner: {winner} (BTC ${self._window_start_price:,.2f} -> ${crypto_price:,.2f})")
                        else:
                            # Fallback to API polling
                            winner = check_market_resolution(self._last_slug, max_wait=15)
                            self.log(f"Winner: {winner or 'unknown'} (API fallback)")
                        for strat in self.strategies:
                            if strat.category == "crypto":
                                strat.on_market_resolve(winner)
                        # Reset window start price for the new window
                        self._window_start_price = crypto_price

                    # Track the BTC price at window start
                    if not self._window_start_price and crypto_price:
                        self._window_start_price = crypto_price

                    self._last_slug = new_slug
                    self._last_market = market

                    # Run crypto strategies
                    for strat in self.strategies:
                        if strat.category == "crypto":
                            try:
                                strat.on_crypto_tick(
                                    crypto_price, market,
                                    self._crypto_prices, time_remaining,
                                )
                            except Exception as e:
                                strat.log(f"ERROR: {e}")

                # === GENERAL TICK (every 5 minutes) ===
                now = time.time()
                if now - self._last_general_scan >= self._general_scan_interval:
                    self._last_general_scan = now
                    try:
                        all_markets = fetch_general_markets(limit=100)
                        if all_markets:
                            for strat in self.strategies:
                                if strat.category == "general":
                                    try:
                                        strat.on_general_tick(all_markets)
                                    except Exception as e:
                                        strat.log(f"ERROR: {e}")
                    except Exception as e:
                        self.log(f"General market scan failed: {e}")

                # Status update every ~60 ticks (~2 min)
                if tick_count % 60 == 1:
                    balances = " | ".join(
                        f"{s.display_name}=${s.balance:.0f}"
                        for s in self.strategies
                    )
                    self.log(f"Tick #{tick_count} | {balances}")

                # Write state for dashboard
                self._write_state("running")

                time.sleep(SCALP_POLL_INTERVAL)

        except KeyboardInterrupt:
            self.log("Interrupted by user.")

        # Final resolution check for any open crypto positions
        if self._last_slug:
            # Try BTC price-based resolution first
            winner = None
            if self._window_start_price and self._last_crypto:
                if self._last_crypto > self._window_start_price:
                    winner = "Up"
                elif self._last_crypto < self._window_start_price:
                    winner = "Down"
                else:
                    winner = "Up"
            if not winner:
                winner = check_market_resolution(self._last_slug, max_wait=15)
            for strat in self.strategies:
                if strat.category == "crypto" and strat.position:
                    strat.on_market_resolve(winner)

        # Stop whale watcher threads
        self.whale_watcher.stop()
        self.log("WhaleWatcher stopped")

        self._write_state("finished")
        self.log("ARENA FINISHED")

        # Print final leaderboard
        self._print_leaderboard()

    def _print_leaderboard(self):
        """Print final standings."""
        results = []
        for s in self.strategies:
            sm = s.summary()
            results.append((s.display_name, sm["balance"], sm["total_pnl"],
                            sm["total_trades"], sm["win_rate"], sm["roi"]))

        results.sort(key=lambda x: x[1], reverse=True)

        print(f"\n{'='*70}")
        print(f"  ARENA FINAL STANDINGS")
        print(f"{'='*70}")
        for i, (name, bal, pnl, trades, wr, roi) in enumerate(results, 1):
            medal = ["", "1ST", "2ND", "3RD"] + [f"{j}TH" for j in range(4, 11)]
            pnl_sign = "+" if pnl >= 0 else ""
            print(f"  {medal[i]:>4} {name:<15} ${bal:>8.2f} ({pnl_sign}{pnl:.2f}) | {trades}T {wr:.0%}WR {roi:+.1f}%ROI")
        print(f"{'='*70}")

    def run_with_state_file(self, duration_minutes=720):
        """Run arena and write state to the standard file."""
        # Clean up old files
        for f in [ARENA_STOP_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass
        self.run(duration_minutes)


# =====================
# CLI
# =====================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Strategy Arena — run 9 strategies overnight")
    parser.add_argument("--duration", type=int, default=720, help="Duration in minutes (default: 720 = 12h)")
    parser.add_argument("--coin", default="btc", help="Crypto coin: btc, eth")
    args = parser.parse_args()

    runner = ArenaRunner(coin=args.coin)
    runner.run_with_state_file(duration_minutes=args.duration)
