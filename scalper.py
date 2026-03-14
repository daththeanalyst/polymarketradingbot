"""
Live Scalper — Crypto Up/Down Markets
======================================
Exploits the 30-90 second lag between crypto spot price moving and
Polymarket odds updating. Buys the underpriced side, then exits
via sell, hedge, or hold-to-resolution.

Supports: BTC, ETH (and any future Polymarket crypto up/down markets).

Runs 3 strategies in parallel for paper trading comparison:
  - Current: standard 3% edge, $5 flat bet
  - Kelly: Kelly criterion bet sizing
  - Aggressive: last-second entries, 1% edge, ride to resolution

Usage:
  python scalper.py              # Dry run — watch and log signals
  python scalper.py --coin eth   # Run on ETH markets
  python bot.py --scalp          # Run from main bot
"""

import os
import csv
import time
import json
import hashlib
import tempfile
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor
from config import (
    GAMMA_API, CLOB_API, BINANCE_API, DRY_RUN,
    SCALP_BET_SIZE, SCALP_POLL_INTERVAL, SCALP_MIN_EDGE,
    SCALP_PROFIT_TARGET, SCALP_STOP_LOSS, SCALP_HEDGE_THRESHOLD,
    SCALP_MARKET_TYPE,
    SCALP_KELLY_ENABLED, SCALP_KELLY_FRACTION, SCALP_KELLY_MIN_EDGE,
    SCALP_KELLY_MAX_BET, SCALP_KELLY_MIN_BET,
    SCALP_AGGRESSIVE_ENABLED, SCALP_AGGRESSIVE_MIN_EDGE,
    SCALP_AGGRESSIVE_BET_SIZE, SCALP_AGGRESSIVE_MAX_TIME,
    SCALP_AGGRESSIVE_MOMENTUM_ONLY,
    SCALP_PAPER_SLIPPAGE, SCALP_PAPER_FEE,
)
from tracker import log_bet
from math_utils import kelly_fraction as calc_kelly, position_size as calc_position_size


# =====================
# STRATEGY CONFIG
# =====================

@dataclass
class StrategyConfig:
    """Configuration for a single scalp strategy variant."""
    name: str                        # "current", "kelly", "aggressive"
    display_name: str                # "Current", "Kelly Criterion", "Aggressive"
    min_edge: float
    bet_size: float
    profit_target: float
    stop_loss: float
    hedge_threshold: float
    use_kelly_sizing: bool = False
    kelly_fraction: float = 0.25
    kelly_max_bet: float = 10.0
    kelly_min_bet: float = 5.0
    last_second_only: bool = False
    max_entry_time: float = 60.0     # For aggressive: only enter with < this many seconds left
    min_entry_time: float = 60.0     # For current/kelly: skip if < this many seconds left
    no_stop_loss: bool = False
    momentum_only: bool = False


STARTING_BALANCE = 100.00  # Each strategy starts with $100 paper balance


@dataclass
class StrategyState:
    """Runtime state for a single strategy's paper trading."""
    config: StrategyConfig
    position: Optional['Position'] = None
    trades: List[Dict] = field(default_factory=list)
    balance: float = STARTING_BALANCE  # Available cash (not in positions)

    def summary(self):
        invested = STARTING_BALANCE - self.balance
        if self.position:
            invested += self.position.entry_cost
        if not self.trades:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "total_pnl": 0, "total_cost": 0, "win_rate": 0, "roi": 0,
                "balance": round(self.balance, 2),
                "starting_balance": STARTING_BALANCE,
            }
        total_pnl = sum(t["pnl"] for t in self.trades)
        total_cost = sum(t.get("cost", t["shares"] * t["entry_price"]) for t in self.trades)
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return {
            "total_trades": len(self.trades),
            "wins": wins,
            "losses": len(self.trades) - wins,
            "total_pnl": round(total_pnl, 4),
            "total_cost": round(total_cost, 4),
            "win_rate": round(wins / len(self.trades), 4),
            "roi": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "balance": round(self.balance, 2),
            "starting_balance": STARTING_BALANCE,
        }


# =====================
# PERSISTENT TRADE LOG (ML training data)
# =====================

TRADE_LOG_FILE = os.path.join(os.path.dirname(__file__), "scalper_trades.csv")
TRADE_LOG_FIELDS = [
    # Identifiers
    "timestamp", "session_id", "strategy", "coin", "market_id", "title",
    # Entry conditions
    "side", "entry_price", "shares", "cost", "edge", "fair_price",
    "momentum", "momentum_window",
    "btc_price_at_entry", "up_price_at_entry", "down_price_at_entry",
    "time_remaining_at_entry", "spread_at_entry",
    # Exit conditions
    "exit_price", "exit_type", "pnl", "pnl_pct", "hold_duration_s",
    "btc_price_at_exit", "up_price_at_exit", "down_price_at_exit",
    "time_remaining_at_exit",
    # Outcome
    "winner", "we_won", "is_live",
]

# Session ID so we can group trades from the same run
_SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")


def _log_trade_to_csv(trade_row):
    """Append a completed trade to the persistent CSV log."""
    file_exists = os.path.exists(TRADE_LOG_FILE)
    try:
        with open(TRADE_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade_row)
    except Exception as e:
        print(f"  [WARN] Failed to log trade: {e}")


def load_trade_history():
    """Load all historical scalper trades from CSV."""
    if not os.path.exists(TRADE_LOG_FILE):
        return []
    try:
        with open(TRADE_LOG_FILE, "r") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception:
        return []


# =====================
# POSITION TRACKING
# =====================

class Position:
    """Tracks a single open scalp position."""
    def __init__(self, side, token_id, opposite_token_id, shares, entry_price, market_id, title, slug="", window_end=0):
        self.side = side
        self.token_id = token_id
        self.opposite_token_id = opposite_token_id
        self.shares = shares
        self.entry_price = entry_price
        self.entry_cost = shares * entry_price
        self.market_id = market_id
        self.title = title
        self.slug = slug
        self.window_end = window_end
        self.entry_time = datetime.now()
        # ML context — set by _enter_strategy after creation
        self.entry_context = {}

    def current_value(self, current_price):
        return self.shares * current_price

    def pnl(self, current_price):
        return self.current_value(current_price) - self.entry_cost

    def pnl_pct(self, current_price):
        if self.entry_cost <= 0:
            return 0
        return (self.current_value(current_price) - self.entry_cost) / self.entry_cost


# =====================
# CRYPTO PRICE FEED
# =====================

# Coin -> Binance symbol mapping
BINANCE_SYMBOLS = {
    "btc": "BTCUSDT",
    "eth": "ETHUSDT",
    "sol": "SOLUSDT",
    "doge": "DOGEUSDT",
}


def get_crypto_price(coin="btc"):
    """Fetch current crypto spot price from Binance."""
    symbol = BINANCE_SYMBOLS.get(coin.lower(), f"{coin.upper()}USDT")
    try:
        resp = requests.get(
            f"{BINANCE_API}/ticker/price",
            params={"symbol": symbol},
            timeout=3,
        )
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception:
        return None


# Backward compat
def get_btc_price():
    return get_crypto_price("btc")


def get_crypto_price_history(coin="btc", minutes=2):
    """Fetch recent crypto prices for momentum calculation."""
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


# Backward compat
def get_btc_price_history(minutes=2):
    return get_crypto_price_history("btc", minutes)


# =====================
# MARKET DISCOVERY
# =====================

# Coin -> timeframe -> (slug_pattern, interval_seconds)
COIN_SLUG_PATTERNS = {
    "btc": {
        "5min":  ("btc-updown-5m-{}",  300),
        "15min": ("btc-updown-15m-{}", 900),
    },
    "eth": {
        "5min":  ("eth-updown-5m-{}",  300),
        "15min": ("eth-updown-15m-{}", 900),
    },
}

# Available coins for the dashboard
AVAILABLE_COINS = list(COIN_SLUG_PATTERNS.keys())

# Legacy alias
SLUG_PATTERNS = COIN_SLUG_PATTERNS["btc"]


def get_live_price(token_id):
    """Fetch real-time midpoint price from CLOB API."""
    try:
        resp = requests.get(
            f"{CLOB_API}/midpoint",
            params={"token_id": token_id},
            timeout=3,
        )
        resp.raise_for_status()
        return float(resp.json().get("mid", 0))
    except Exception:
        return None


def _fetch_gamma_event(slug):
    """Helper: fetch event from Gamma API. Returns (event, market) or None."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": slug},
            timeout=3,
        )
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


def fetch_all_data_parallel(market_type="5min", coin="btc"):
    """
    Fetch crypto price + market data in parallel.
    Returns (price, market_dict_or_None).
    Saves ~500ms per iteration vs sequential.
    """
    coin = coin.lower()
    coin_patterns = COIN_SLUG_PATTERNS.get(coin, COIN_SLUG_PATTERNS.get("btc", {}))
    pattern, interval = coin_patterns.get(market_type, coin_patterns.get("5min", ("btc-updown-5m-{}", 300)))
    now = int(time.time())
    window_ts = (now // interval) * interval
    slug = pattern.format(window_ts)

    # Phase 1: crypto price + Gamma market discovery in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        price_future = pool.submit(get_crypto_price, coin)
        gamma_future = pool.submit(_fetch_gamma_event, slug)
        btc_price = price_future.result()
        gamma_result = gamma_future.result()

    if not gamma_result:
        return btc_price, None

    event, market = gamma_result
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
        gamma_prices = json.loads(market.get("outcomePrices", "[]"))
    except (json.JSONDecodeError, TypeError):
        return btc_price, None

    if len(outcomes) < 2 or len(token_ids) < 2 or len(gamma_prices) < 2:
        return btc_price, None

    # Phase 2: Both CLOB midpoints in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        up_future = pool.submit(get_live_price, token_ids[0])
        down_future = pool.submit(get_live_price, token_ids[1])
        up_live = up_future.result()
        down_live = down_future.result()

    up_price = up_live if up_live and up_live > 0 else float(gamma_prices[0])
    down_price = down_live if down_live and down_live > 0 else float(gamma_prices[1])

    return btc_price, {
        "id": market.get("id", ""),
        "condition_id": market.get("conditionId", ""),
        "title": event.get("title", ""),
        "slug": slug,
        "up_price": up_price,
        "down_price": down_price,
        "up_token": token_ids[0],
        "down_token": token_ids[1],
        "volume": float(event.get("volume", 0) or 0),
        "end_date": event.get("endDate", ""),
        "accepting_orders": market.get("acceptingOrders", False),
        "order_min_size": market.get("orderMinSize", 5),
        "window_end": window_ts + interval,
    }


# Keep original for standalone/backward compat
def find_active_crypto_market(market_type="5min", coin="btc"):
    """Find active crypto market (single-threaded version for simple callers)."""
    _, market = fetch_all_data_parallel(market_type, coin)
    return market


def get_time_remaining(market):
    """Seconds remaining until market resolves."""
    window_end = market.get("window_end")
    if window_end:
        return max(0, window_end - time.time())
    end_str = market.get("end_date", "")
    if not end_str:
        return 300
    try:
        end_str = end_str.replace("Z", "+00:00")
        end_dt = datetime.fromisoformat(end_str)
        now = datetime.now(timezone.utc)
        return max(0, (end_dt - now).total_seconds())
    except Exception:
        return 300


def check_resolution(slug, max_wait=90):
    """
    After a market window ends, poll to see which side won.
    Returns "Up", "Down", or None.
    """
    for _ in range(max_wait // 5):
        try:
            resp = requests.get(
                f"{GAMMA_API}/events",
                params={"slug": slug},
                timeout=10,
            )
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
# SIGNAL DETECTION
# =====================

def detect_entry_signal_with_edge(btc_prices, market, min_edge):
    """
    Detect when BTC spot price movement disagrees with market odds.
    Configurable min_edge parameter for different strategies.
    Returns: ("UP", edge, fair_price) or ("DOWN", edge, fair_price) or None
    """
    if len(btc_prices) < 2:
        return None

    oldest = btc_prices[0]
    newest = btc_prices[-1]
    if oldest <= 0:
        return None

    momentum = (newest - oldest) / oldest
    up_price = market["up_price"]
    down_price = market["down_price"]

    momentum_signal = momentum * 50
    fair_up = max(0.10, min(0.90, 0.50 + momentum_signal))
    fair_down = 1.0 - fair_up

    up_edge = fair_up - up_price
    if up_edge > min_edge:
        return ("UP", round(up_edge, 4), round(fair_up, 4))

    down_edge = fair_down - down_price
    if down_edge > min_edge:
        return ("DOWN", round(down_edge, 4), round(fair_down, 4))

    return None


def detect_entry_signal(btc_prices, market):
    """Original signal detection (uses global SCALP_MIN_EDGE)."""
    return detect_entry_signal_with_edge(btc_prices, market, SCALP_MIN_EDGE)


def detect_kelly_signal(btc_prices, market, config):
    """
    Kelly strategy: standard signal + Kelly criterion bet sizing.
    Returns: ("UP"/"DOWN", edge, fair_price, bet_size) or None
    """
    signal = detect_entry_signal_with_edge(btc_prices, market, config.min_edge)
    if not signal:
        return None

    side, edge, fair_price = signal
    market_price = market["up_price"] if side == "UP" else market["down_price"]

    # Kelly says what fraction of bankroll to bet
    kelly_f = calc_kelly(fair_price, market_price, fee_rate=0.02)
    if kelly_f <= 0:
        return None  # Kelly says no edge after fees

    # Size the bet using quarter-Kelly on a $100 notional bankroll
    bet_size = calc_position_size(
        fair_price, market_price, bankroll=100.0,
        fraction=config.kelly_fraction, fee_rate=0.02,
        max_pct=config.kelly_max_bet / 100.0,
    )
    bet_size = max(config.kelly_min_bet, min(bet_size, config.kelly_max_bet))

    return (side, edge, fair_price, bet_size)


def detect_aggressive_signal(btc_prices, market, config, time_remaining):
    """
    Aggressive last-second strategy: low edge, enters only in final seconds.
    Returns: ("UP"/"DOWN", edge, fair_price) or None
    """
    # Only enter during the last N seconds
    if time_remaining > config.max_entry_time:
        return None
    if time_remaining < 5:
        return None  # Too close, market likely frozen

    # Try standard signal with low edge threshold
    signal = detect_entry_signal_with_edge(btc_prices, market, config.min_edge)
    if signal:
        return signal

    # Momentum-only: if BTC is clearly moving, enter on raw momentum
    if config.momentum_only and len(btc_prices) >= 3:
        recent = btc_prices[-6:] if len(btc_prices) >= 6 else btc_prices
        oldest = recent[0]
        newest = recent[-1]
        if oldest <= 0:
            return None

        momentum = (newest - oldest) / oldest

        # Strong momentum (> 0.1% in ~12 seconds) -> enter
        if abs(momentum) > 0.001:
            if momentum > 0:
                fair_up = min(0.90, 0.50 + momentum * 50)
                edge = fair_up - market["up_price"]
                if edge > 0:
                    return ("UP", round(edge, 4), round(fair_up, 4))
            else:
                fair_down = min(0.90, 0.50 + abs(momentum) * 50)
                edge = fair_down - market["down_price"]
                if edge > 0:
                    return ("DOWN", round(edge, 4), round(fair_down, 4))

    return None


# =====================
# EXIT LOGIC
# =====================

def check_exit(position, current_price, opposite_price, time_remaining):
    """Standard exit logic (used by 'current' strategy)."""
    return check_exit_for_strategy(
        position, current_price, opposite_price, time_remaining,
        StrategyConfig(
            name="current", display_name="Current",
            min_edge=SCALP_MIN_EDGE, bet_size=SCALP_BET_SIZE,
            profit_target=SCALP_PROFIT_TARGET, stop_loss=SCALP_STOP_LOSS,
            hedge_threshold=SCALP_HEDGE_THRESHOLD,
        )
    )


def check_exit_for_strategy(position, current_price, opposite_price, time_remaining, config):
    """
    Strategy-aware exit logic.
    Aggressive: no stop loss, rides to resolution.
    Kelly/Current: configurable thresholds.
    """
    pnl_pct = position.pnl_pct(current_price)
    pnl_dollar = position.pnl(current_price)

    # Aggressive: no early exit, ride to resolution
    if config.no_stop_loss:
        if pnl_pct >= config.profit_target:
            return ("SELL", f"Profit target: {pnl_pct:+.0%}")
        return ("HOLD", f"Riding: {pnl_pct:+.0%} (${pnl_dollar:+.2f}), {time_remaining:.0f}s left")

    # Take profit
    if pnl_pct >= config.profit_target:
        return ("SELL", f"Profit target hit: {pnl_pct:+.0%} (${pnl_dollar:+.2f})")

    # Hold to resolution if winning and almost done
    if time_remaining < 15 and pnl_pct > 0:
        return ("HOLD", f"Holding to resolution: {time_remaining:.0f}s left, {pnl_pct:+.0%}")

    # Stop loss with hedge check
    if pnl_pct < -config.stop_loss:
        hedge_cost = position.shares * opposite_price
        total_cost = position.entry_cost + hedge_cost
        guaranteed_payout = position.shares * 1.0
        if guaranteed_payout > total_cost:
            locked_profit = guaranteed_payout - total_cost
            return ("HEDGE", f"Hedge to lock ${locked_profit:.2f} profit (was {pnl_pct:+.0%})")
        return ("SELL", f"Stop loss: {pnl_pct:+.0%} (${pnl_dollar:+.2f}), hedge unprofitable")

    # Cut losses if time running out
    if time_remaining < 30 and pnl_pct < -0.10:
        return ("SELL", f"Time running out ({time_remaining:.0f}s), cutting loss: {pnl_pct:+.0%}")

    return ("HOLD", f"Watching: {pnl_pct:+.0%} (${pnl_dollar:+.2f}), {time_remaining:.0f}s left")


# =====================
# LIVE vs PAPER TRADING
# =====================

def cfg_name_matches_live(name):
    """Only the 'current' strategy places real orders. Others are always paper."""
    return name == "current"


# =====================
# MAIN SCALPING LOOP
# =====================

class LiveScalper:
    """
    Runs a live scalping loop on 5-minute BTC markets.
    Evaluates 3 strategies per iteration, tracks independent virtual positions.
    """

    def __init__(self, trader, coin="btc"):
        self.trader = trader
        self.coin = coin.lower()
        self.coin_label = coin.upper()
        self.btc_prices = []  # kept as "btc_prices" for backward compat but holds any coin
        self._log_lines = []
        self._state_file = None
        self._last_btc = None
        self._last_market = None
        self._last_state_hash = None
        self._max_window = 12  # ~24 seconds at 2s polling

        # Build strategy configs
        current_config = StrategyConfig(
            name="current", display_name="Current",
            min_edge=SCALP_MIN_EDGE, bet_size=SCALP_BET_SIZE,
            profit_target=SCALP_PROFIT_TARGET, stop_loss=SCALP_STOP_LOSS,
            hedge_threshold=SCALP_HEDGE_THRESHOLD, min_entry_time=60.0,
        )
        kelly_config = StrategyConfig(
            name="kelly", display_name="Kelly Criterion",
            min_edge=SCALP_KELLY_MIN_EDGE, bet_size=SCALP_KELLY_MIN_BET,
            profit_target=SCALP_PROFIT_TARGET, stop_loss=SCALP_STOP_LOSS,
            hedge_threshold=SCALP_HEDGE_THRESHOLD,
            use_kelly_sizing=True, kelly_fraction=SCALP_KELLY_FRACTION,
            kelly_max_bet=SCALP_KELLY_MAX_BET, kelly_min_bet=SCALP_KELLY_MIN_BET,
            min_entry_time=60.0,
        )
        aggressive_config = StrategyConfig(
            name="aggressive", display_name="Aggressive",
            min_edge=SCALP_AGGRESSIVE_MIN_EDGE, bet_size=SCALP_AGGRESSIVE_BET_SIZE,
            profit_target=1.0, stop_loss=1.0, hedge_threshold=1.0,
            last_second_only=True, max_entry_time=SCALP_AGGRESSIVE_MAX_TIME,
            min_entry_time=0.0, no_stop_loss=True,
            momentum_only=SCALP_AGGRESSIVE_MOMENTUM_ONLY,
        )

        self.strategies = [StrategyState(config=current_config)]
        if SCALP_KELLY_ENABLED:
            self.strategies.append(StrategyState(config=kelly_config))
        if SCALP_AGGRESSIVE_ENABLED:
            self.strategies.append(StrategyState(config=aggressive_config))

        # Legacy aliases (backward compat)
        self.position = None
        self.trades = []

    def log(self, msg):
        """Print with timestamp and store for state file."""
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(f"  {line}")
        self._log_lines.append(line)
        if len(self._log_lines) > 50:
            self._log_lines = self._log_lines[-50:]

    def _write_state(self, status="running"):
        """Write current state to JSON file for dashboard to read."""
        if not self._state_file:
            return

        # Build per-strategy state
        strategies_data = {}
        for strat in self.strategies:
            cfg = strat.config
            pos_data = None
            if strat.position:
                pos = strat.position
                current_price = 0.50
                if self._last_market:
                    current_price = self._last_market["up_price"] if pos.side == "UP" else self._last_market["down_price"]
                pos_data = {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "shares": pos.shares,
                    "cost": round(pos.entry_cost, 4),
                    "current_pnl": round(pos.pnl(current_price), 4),
                    "current_pnl_pct": round(pos.pnl_pct(current_price), 4),
                    "title": pos.title,
                }

            strategies_data[cfg.name] = {
                "display_name": cfg.display_name,
                "config": {
                    "min_edge": cfg.min_edge,
                    "bet_size": cfg.bet_size,
                    "use_kelly": cfg.use_kelly_sizing,
                    "last_second_only": cfg.last_second_only,
                    "no_stop_loss": cfg.no_stop_loss,
                },
                "position": pos_data,
                "trades": strat.trades,
                "summary": strat.summary(),
            }

        market_data = None
        if self._last_market:
            m = self._last_market
            market_data = {
                "title": m.get("title", ""),
                "slug": m.get("slug", ""),
                "up_price": m.get("up_price", 0),
                "down_price": m.get("down_price", 0),
                "time_remaining": round(get_time_remaining(m)),
            }

        state = {
            "status": status,
            "pid": os.getpid(),
            "timestamp": datetime.now().isoformat(),
            "dry_run": DRY_RUN,
            "coin": self.coin,
            "coin_label": self.coin_label,
            "btc_price": self._last_btc,  # kept as btc_price for backward compat
            "market": market_data,
            "strategies": strategies_data,
            # Legacy fields: point to "current" strategy for backward compat
            "position": strategies_data.get("current", {}).get("position"),
            "trades": strategies_data.get("current", {}).get("trades", []),
            "summary": strategies_data.get("current", {}).get("summary", {}),
            "log": self._log_lines[-30:],
        }

        # Only write if state actually changed
        state_json = json.dumps(state, indent=2, sort_keys=True)
        state_hash = hashlib.md5(state_json.encode()).hexdigest()
        if state_hash == self._last_state_hash:
            return
        self._last_state_hash = state_hash

        # Atomic write
        try:
            dir_name = os.path.dirname(self._state_file) or "."
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                f.write(state_json)
            os.replace(tmp_path, self._state_file)
        except Exception:
            pass

    def _is_live_strategy(self, strat):
        """Check if this strategy should place real orders (not just paper trade)."""
        return cfg_name_matches_live(strat.config.name) and not DRY_RUN

    def _enter_strategy(self, strat, side, market, bet_size, edge=0, fair_price=0):
        """Enter a position for a specific strategy. Places real orders if live."""
        cfg = strat.config
        if side == "UP":
            token_id = market["up_token"]
            opposite_token = market["down_token"]
            raw_price = market["up_price"]
        else:
            token_id = market["down_token"]
            opposite_token = market["up_token"]
            raw_price = market["down_price"]

        # Paper trading: simulate slippage (you pay more than displayed price)
        is_live = self._is_live_strategy(strat)
        if not is_live:
            price = min(raw_price * (1 + SCALP_PAPER_SLIPPAGE), 0.99)
        else:
            price = raw_price

        shares = round(bet_size / price, 2) if price > 0 else 0
        actual_cost = round(shares * price, 4)
        min_size = market.get("order_min_size", 5)
        if shares < min_size:
            self.log(f"[{cfg.display_name}] Skip: {shares:.1f} shares < min {min_size}")
            return

        # Check balance
        if strat.balance < actual_cost:
            self.log(f"[{cfg.display_name}] Skip: insufficient balance (${strat.balance:.2f} < ${actual_cost:.2f})")
            return

        # Deduct cost from balance
        strat.balance -= actual_cost

        mode = "LIVE" if self._is_live_strategy(strat) else "PAPER"
        self.log(f"[{cfg.display_name}] [{mode}] ENTER: {side} {shares:.1f} shares @ ${price:.3f} | Cost: ${actual_cost:.2f} | Bal: ${strat.balance:.2f}")

        # Place real order for the "current" strategy (other strategies are always paper)
        if cfg.name == "current":
            self.trader.place_limit_order(token_id, "BUY", bet_size, price)
            log_bet({
                "market_id": market["id"],
                "title": market["title"],
                "side": side,
                "yes_price": price,
                "bet_amount": bet_size,
                "shares": shares,
                "forecast_prob": 0,
                "category": "scalp",
            }, strategy="scalp")

        # Calculate momentum for ML context
        momentum = 0.0
        momentum_window = len(self.btc_prices)
        if len(self.btc_prices) >= 2:
            momentum = (self.btc_prices[-1] - self.btc_prices[0]) / self.btc_prices[0]

        time_remaining = get_time_remaining(market)

        strat.position = Position(
            side=side, token_id=token_id, opposite_token_id=opposite_token,
            shares=shares, entry_price=price, market_id=market["id"],
            title=market["title"], slug=market.get("slug", ""),
            window_end=market.get("window_end", 0),
        )
        # Store entry context for ML logging at exit
        strat.position.entry_context = {
            "edge": round(edge, 6),
            "fair_price": round(fair_price, 4),
            "momentum": round(momentum, 8),
            "momentum_window": momentum_window,
            "btc_price": self._last_btc or 0,
            "up_price": market["up_price"],
            "down_price": market["down_price"],
            "time_remaining": round(time_remaining, 1),
            "spread": round(market["up_price"] + market["down_price"] - 1.0, 4),
            "is_live": self._is_live_strategy(strat),
        }

    def _build_trade_csv_row(self, strat, pos, exit_price, exit_type, pnl, winner=None, we_won=None):
        """Build a CSV row with full ML context from entry + exit."""
        ctx = pos.entry_context or {}
        hold_s = (datetime.now() - pos.entry_time).total_seconds()
        pnl_pct = round(pnl / pos.entry_cost, 4) if pos.entry_cost > 0 else 0

        # Current market state at exit
        exit_up = self._last_market.get("up_price", 0) if self._last_market else 0
        exit_down = self._last_market.get("down_price", 0) if self._last_market else 0
        exit_time_remaining = get_time_remaining(self._last_market) if self._last_market else 0

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": _SESSION_ID,
            "strategy": strat.config.name,
            "coin": self.coin,
            "market_id": pos.market_id,
            "title": (pos.title or "")[:80],
            # Entry
            "side": pos.side,
            "entry_price": round(pos.entry_price, 4),
            "shares": round(pos.shares, 2),
            "cost": round(pos.entry_cost, 4),
            "edge": ctx.get("edge", ""),
            "fair_price": ctx.get("fair_price", ""),
            "momentum": ctx.get("momentum", ""),
            "momentum_window": ctx.get("momentum_window", ""),
            "btc_price_at_entry": ctx.get("btc_price", ""),
            "up_price_at_entry": ctx.get("up_price", ""),
            "down_price_at_entry": ctx.get("down_price", ""),
            "time_remaining_at_entry": ctx.get("time_remaining", ""),
            "spread_at_entry": ctx.get("spread", ""),
            # Exit
            "exit_price": round(exit_price, 4),
            "exit_type": exit_type,
            "pnl": round(pnl, 4),
            "pnl_pct": pnl_pct,
            "hold_duration_s": round(hold_s, 1),
            "btc_price_at_exit": self._last_btc or "",
            "up_price_at_exit": round(exit_up, 4),
            "down_price_at_exit": round(exit_down, 4),
            "time_remaining_at_exit": round(exit_time_remaining, 1),
            # Outcome
            "winner": winner or "",
            "we_won": we_won if we_won is not None else "",
            "is_live": ctx.get("is_live", False),
        }

    def _finalize_trade(self, strat, trade_dict, pnl):
        """Append trade to in-memory list, credit balance, log to CSV."""
        strat.trades.append(trade_dict)
        # Credit proceeds back to balance: entry cost + pnl
        proceeds = strat.position.entry_cost + pnl
        strat.balance += max(0, proceeds)  # Can't receive negative from a trade
        self.log(f"[{strat.config.display_name}] Balance: ${strat.balance:.2f}")
        # Persist to CSV
        csv_row = self._build_trade_csv_row(
            strat, strat.position,
            exit_price=trade_dict["exit_price"],
            exit_type=trade_dict["exit_type"],
            pnl=pnl,
            winner=trade_dict.get("winner"),
            we_won=trade_dict.get("we_won"),
        )
        _log_trade_to_csv(csv_row)
        strat.position = None

    def _exit_strategy_sell(self, strat, current_price):
        """Exit a strategy's position by selling. Places real sell if live."""
        pos = strat.position
        is_live = self._is_live_strategy(strat)
        # Paper trading: simulate slippage on sell (you get slightly less)
        if not is_live:
            sell_price = current_price * (1 - SCALP_PAPER_SLIPPAGE)
        else:
            sell_price = current_price
        pnl = pos.pnl(sell_price)
        mode = "LIVE" if is_live else "PAPER"
        self.log(f"[{strat.config.display_name}] [{mode}] SELL: {pos.shares:.1f} shares @ ${sell_price:.3f} | P&L: ${pnl:+.2f}")

        # Place real sell order for live strategy
        if strat.config.name == "current":
            self.trader.sell_position(pos.token_id, pos.shares, min_price=current_price)

        self._finalize_trade(strat, {
            "strategy": strat.config.name,
            "side": pos.side, "entry_price": pos.entry_price,
            "exit_price": sell_price, "shares": pos.shares,
            "cost": round(pos.entry_cost, 4), "pnl": round(pnl, 4),
            "exit_type": "sell", "title": pos.title,
        }, pnl)

    def _exit_strategy_hedge(self, strat, opposite_price):
        """Exit a strategy's position by hedging (buying opposite side). Places real order if live."""
        pos = strat.position
        hedge_cost = pos.shares * opposite_price
        guaranteed_payout = pos.shares * 1.0
        locked_pnl = guaranteed_payout - pos.entry_cost - hedge_cost
        mode = "LIVE" if self._is_live_strategy(strat) else "PAPER"
        self.log(f"[{strat.config.display_name}] [{mode}] HEDGE: locked ${locked_pnl:+.2f}")

        # Place real hedge (buy opposite side) for live strategy
        if strat.config.name == "current":
            self.trader.place_limit_order(pos.opposite_token_id, "BUY", hedge_cost, opposite_price)

        # Hedge also costs money from balance (buying the opposite side)
        strat.balance -= hedge_cost

        self._finalize_trade(strat, {
            "strategy": strat.config.name,
            "side": pos.side, "entry_price": pos.entry_price,
            "exit_price": opposite_price, "shares": pos.shares,
            "cost": round(pos.entry_cost, 4), "pnl": round(locked_pnl, 4),
            "exit_type": "hedge", "title": pos.title,
        }, locked_pnl)

    def _resolve_strategy(self, strat, winner):
        """Handle market resolution for a strategy's open position."""
        pos = strat.position
        cfg = strat.config
        we_won = False

        is_live = self._is_live_strategy(strat)

        if winner:
            we_won = (
                (pos.side == "UP" and winner == "Up") or
                (pos.side == "DOWN" and winner == "Down")
            )
            if we_won:
                payout = pos.shares * 1.0
                # Apply fee on winnings (profit portion only)
                winnings = payout - pos.entry_cost
                fee = winnings * SCALP_PAPER_FEE if (not is_live and winnings > 0) else 0
                pnl = winnings - fee
                self.log(f"[{cfg.display_name}] WIN! P&L: ${pnl:+.2f} (fee: ${fee:.2f})")
            else:
                pnl = -pos.entry_cost
                self.log(f"[{cfg.display_name}] LOSS. Lost: ${pos.entry_cost:.2f}")
            exit_price = 1.0 if we_won else 0.0
        else:
            current_price = 0.50
            if self._last_market:
                current_price = self._last_market["up_price"] if pos.side == "UP" else self._last_market["down_price"]
            pnl = pos.pnl(current_price)
            exit_price = current_price
            self.log(f"[{cfg.display_name}] Resolution unknown. Est P&L: ${pnl:+.2f}")

        self._finalize_trade(strat, {
            "strategy": cfg.name,
            "side": pos.side, "entry_price": pos.entry_price,
            "exit_price": exit_price, "shares": pos.shares,
            "cost": round(pos.entry_cost, 4), "pnl": round(pnl, 4),
            "exit_type": "resolution", "winner": winner or "unknown",
            "we_won": we_won, "title": pos.title,
        }, pnl)

    def run(self, duration_minutes=30):
        """
        Main scalping loop. Fetches data in parallel, evaluates all strategies,
        manages positions independently per strategy.
        """
        print(f"\n{'='*60}")
        print(f"  LIVE SCALPER - {SCALP_MARKET_TYPE} {self.coin_label} Markets")
        if DRY_RUN:
            print(f"  Mode: PAPER TRADING (no real money)")
        else:
            print(f"  *** LIVE TRADING MODE — REAL MONEY ***")
            print(f"  *** The 'Current' strategy WILL place real orders ***")
        print(f"  Strategies: {', '.join(s.config.display_name for s in self.strategies)}")
        print(f"  Poll interval: {SCALP_POLL_INTERVAL}s | Duration: {duration_minutes} min")
        print(f"{'='*60}\n")

        # Seed price history
        self.log(f"Loading {self.coin_label} price history...")
        history = get_crypto_price_history(self.coin, minutes=2)
        if history:
            self.btc_prices = history
            self.log(f"{self.coin_label} at ${history[-1]:,.2f} (loaded {len(history)} data points)")
        else:
            self.log("WARNING: Could not load price history")

        end_time = time.time() + (duration_minutes * 60)
        scan_count = 0

        try:
            while time.time() < end_time:
                scan_count += 1

                # Check for stop signal
                if self._check_stop_signal():
                    self.log("Stop requested.")
                    break

                # Fetch crypto price + market data in parallel
                btc, market = fetch_all_data_parallel(SCALP_MARKET_TYPE, self.coin)
                self._last_btc = btc

                if btc:
                    self.btc_prices.append(btc)
                    if len(self.btc_prices) > self._max_window:
                        self.btc_prices = self.btc_prices[-self._max_window:]

                if not btc:
                    self.log("Failed to get BTC price, retrying...")
                    time.sleep(SCALP_POLL_INTERVAL)
                    continue

                if not market:
                    if scan_count % 12 == 1:
                        self.log(f"No active {SCALP_MARKET_TYPE} BTC market found...")
                    time.sleep(SCALP_POLL_INTERVAL)
                    continue

                if not market.get("accepting_orders", True):
                    if scan_count % 12 == 1:
                        self.log(f"Market {market['slug']} not accepting orders...")
                    time.sleep(SCALP_POLL_INTERVAL)
                    continue

                self._last_market = market
                time_remaining = get_time_remaining(market)

                # Status update every ~60 iterations (~2 min at 2s polling)
                if scan_count % 30 == 1:
                    strat_summary = " | ".join(
                        f"{s.config.display_name}: {len(s.trades)}T"
                        for s in self.strategies
                    )
                    self.log(f"{self.coin_label} ${btc:,.2f} | UP={market['up_price']:.2f} DOWN={market['down_price']:.2f} | {time_remaining:.0f}s | {strat_summary}")

                # --- Run all strategies ---
                for strat in self.strategies:
                    cfg = strat.config

                    # No position -> look for entry
                    if strat.position is None:
                        signal = None
                        bet_size = cfg.bet_size

                        if cfg.name == "current":
                            if time_remaining > cfg.min_entry_time:
                                signal = detect_entry_signal_with_edge(self.btc_prices, market, cfg.min_edge)

                        elif cfg.name == "kelly":
                            if time_remaining > cfg.min_entry_time:
                                kelly_result = detect_kelly_signal(self.btc_prices, market, cfg)
                                if kelly_result:
                                    side, edge, fair_price, kelly_bet = kelly_result
                                    signal = (side, edge, fair_price)
                                    bet_size = kelly_bet

                        elif cfg.name == "aggressive":
                            signal = detect_aggressive_signal(self.btc_prices, market, cfg, time_remaining)

                        if signal:
                            side, edge, fair_price = signal
                            self.log(f"[{cfg.display_name}] SIGNAL: {side} | Edge: {edge:+.1%} | Fair: {fair_price:.2f}")
                            self._enter_strategy(strat, side, market, bet_size, edge=edge, fair_price=fair_price)

                    # Has position -> check exit
                    else:
                        pos = strat.position
                        if pos.side == "UP":
                            current_price = market["up_price"]
                            opposite_price = market["down_price"]
                        else:
                            current_price = market["down_price"]
                            opposite_price = market["up_price"]

                        action, reason = check_exit_for_strategy(pos, current_price, opposite_price, time_remaining, cfg)

                        if action == "SELL":
                            self.log(f"[{cfg.display_name}] EXIT: {reason}")
                            self._exit_strategy_sell(strat, current_price)
                        elif action == "HEDGE":
                            self.log(f"[{cfg.display_name}] EXIT: {reason}")
                            self._exit_strategy_hedge(strat, opposite_price)
                        elif scan_count % 15 == 0:
                            self.log(f"[{cfg.display_name}] {reason}")

                        # Market resolved while holding
                        if time_remaining <= 0 and strat.position:
                            self.log(f"[{cfg.display_name}] Market ended, checking resolution...")
                            # Resolution is checked once below (shared across strategies)

                # Check resolution once for all strategies with open positions
                if time_remaining <= 0:
                    strategies_with_positions = [s for s in self.strategies if s.position]
                    if strategies_with_positions:
                        slug = strategies_with_positions[0].position.slug
                        self.log(f"Checking resolution for {slug}...")
                        winner = check_resolution(slug)
                        for strat in strategies_with_positions:
                            self._resolve_strategy(strat, winner)

                self._write_state("running")
                time.sleep(SCALP_POLL_INTERVAL)

        except KeyboardInterrupt:
            self.log("Stopped by user (Ctrl+C)")

        # End of session: resolve any remaining positions
        for strat in self.strategies:
            if strat.position:
                pos = strat.position
                time_left = max(0, pos.window_end - time.time()) if pos.window_end else 0
                if time_left > 0:
                    self.log(f"[{strat.config.display_name}] Waiting {time_left:.0f}s for resolution...")
                    time.sleep(time_left + 5)

                self.log(f"[{strat.config.display_name}] Final resolution check...")
                winner = check_resolution(pos.slug)
                self._resolve_strategy(strat, winner)

        self.print_summary()

    def _check_stop_signal(self):
        """Check if dashboard requested a stop."""
        if not self._state_file:
            return False
        stop_file = self._state_file + ".stop"
        if os.path.exists(stop_file):
            try:
                os.remove(stop_file)
            except OSError:
                pass
            return True
        return False

    def run_with_state_file(self, duration_minutes=30, state_file="scalper_state.json"):
        """Same as run() but writes state to a JSON file every poll cycle."""
        self._state_file = state_file
        self._log_lines = []
        self._last_state_hash = None

        stop_file = state_file + ".stop"
        if os.path.exists(stop_file):
            try:
                os.remove(stop_file)
            except OSError:
                pass

        self._write_state("starting")
        self.run(duration_minutes=duration_minutes)
        self._write_state("finished")

    def print_summary(self):
        """Print paper trading session report for all strategies."""
        print(f"\n{'='*60}")
        print(f"  PAPER TRADING SESSION REPORT")
        print(f"{'='*60}")

        for strat in self.strategies:
            cfg = strat.config
            trades = strat.trades

            print(f"\n  --- {cfg.display_name} Strategy ---")

            if not trades:
                print(f"  No trades this session.")
                continue

            total_pnl = sum(t["pnl"] for t in trades)
            total_cost = sum(t.get("cost", 0) for t in trades)
            total_return = total_cost + total_pnl
            wins = sum(1 for t in trades if t["pnl"] > 0)
            losses = len(trades) - wins
            win_rate = wins / len(trades) * 100 if trades else 0
            roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0

            print(f"  Trades: {len(trades)} | Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.0f}%")
            print(f"  Invested: ${total_cost:.2f} -> Returned: ${total_return:.2f}")
            print(f"  P&L: ${total_pnl:+.2f} | ROI: {roi:+.1f}%")

            print(f"\n  {'-'*56}")
            print(f"  {'#':<4} {'Side':<6} {'Entry':>7} {'Exit':>7} {'Type':<12} {'Invested':>9} {'Returned':>9} {'P&L':>8}")
            print(f"  {'-'*56}")

            for i, t in enumerate(trades, 1):
                cost = t.get("cost", t["shares"] * t["entry_price"])
                returned = cost + t["pnl"]
                result = "WIN" if t["pnl"] > 0 else "LOSS"
                exit_label = t["exit_type"]
                if t.get("winner") and t["exit_type"] == "resolution":
                    exit_label = f"res:{t['winner']}"

                print(f"  {i:<4} {t['side']:<6} ${t['entry_price']:.3f}  ${t['exit_price']:.3f}  {exit_label:<12} ${cost:.2f}    ${returned:.2f}   ${t['pnl']:+.2f} {result}")

            print(f"  {'-'*56}")

        print(f"\n{'='*60}")


# --- Run standalone ---
if __name__ == "__main__":
    import argparse as _ap
    from trader import Trader

    _parser = _ap.ArgumentParser()
    _parser.add_argument("--coin", default="btc", help="Coin: btc, eth")
    _parser.add_argument("--duration", type=int, default=30, help="Duration in minutes")
    _args = _parser.parse_args()

    coin = _args.coin.upper()
    print("=" * 60)
    print(f"LIVE SCALPER - {coin} Markets (3 Strategies)")
    print("=" * 60)

    trader = Trader()
    trader.connect()

    scalper = LiveScalper(trader, coin=_args.coin)
    scalper.run(duration_minutes=_args.duration)
