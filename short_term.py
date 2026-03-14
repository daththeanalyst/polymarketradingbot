"""
Short-Term Crypto Market Scanner
==================================
Trades 5-minute, 15-minute, and hourly crypto price markets on Polymarket.
Uses real-time price data from free APIs (CoinGecko, Binance) to identify
mispriced short-term crypto markets based on momentum signals.

Usage:
  python short_term.py             # Scan for short-term opportunities
  python bot.py --short-term       # Run from main bot
"""

import re
import requests
from config import (
    GAMMA_API, COINGECKO_API, BINANCE_API,
    SHORT_TERM_MIN_EDGE, SHORT_TERM_BET_SIZE,
    SHORT_TERM_MAX_POSITIONS, SHORT_TERM_COINS,
)
from markets import _normalize_market
from math_utils import from_log_odds


# =====================
# PRICE DATA (Free APIs)
# =====================

def fetch_current_prices():
    """
    Get current prices for BTC/ETH from CoinGecko (free, no API key).
    Falls back to Binance if CoinGecko fails.
    Returns dict like {"bitcoin": 85000.50, "ethereum": 3200.10}
    """
    # Try CoinGecko first
    try:
        ids = ",".join(SHORT_TERM_COINS)
        resp = requests.get(
            f"{COINGECKO_API}/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {coin: data[coin]["usd"] for coin in SHORT_TERM_COINS if coin in data}
    except Exception:
        pass

    # Fallback to Binance
    try:
        prices = {}
        symbol_map = {"bitcoin": "BTCUSDT", "ethereum": "ETHUSDT"}
        for coin in SHORT_TERM_COINS:
            symbol = symbol_map.get(coin)
            if not symbol:
                continue
            resp = requests.get(
                f"{BINANCE_API}/ticker/price",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            prices[coin] = float(resp.json()["price"])
        return prices
    except Exception as e:
        print(f"  [ERROR] Could not fetch crypto prices: {e}")
        return {}


def fetch_price_history(coin_id="bitcoin", hours=24):
    """
    Get recent price history from CoinGecko for momentum calculation.
    Returns list of prices (newest last), sampled at ~5min intervals.
    """
    try:
        resp = requests.get(
            f"{COINGECKO_API}/coins/{coin_id}/market_chart",
            params={"vs_currency": "usd", "days": "1"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # data["prices"] = [[timestamp_ms, price], ...]
        return [p[1] for p in data.get("prices", [])]
    except Exception as e:
        print(f"  [ERROR] Price history failed for {coin_id}: {e}")
        return []


# =====================
# TECHNICAL INDICATORS
# =====================

def calculate_rsi(prices, period=14):
    """
    Calculate Relative Strength Index.
    RSI > 70 = overbought (likely to go DOWN)
    RSI < 30 = oversold (likely to go UP)
    Returns RSI value (0-100) or None if insufficient data.
    """
    if len(prices) < period + 1:
        return None

    # Use last (period + 1) prices
    recent = prices[-(period + 1):]
    gains = []
    losses = []

    for i in range(1, len(recent)):
        change = recent[i] - recent[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


def calculate_momentum(prices, window=5):
    """
    Simple momentum: compare current price to price N periods ago.
    Returns a value between -1.0 (strong down) and +1.0 (strong up).
    """
    if len(prices) < window + 1:
        return 0.0

    current = prices[-1]
    past = prices[-(window + 1)]

    if past == 0:
        return 0.0

    pct_change = (current - past) / past

    # Clamp to [-1, 1] range (10% move = max signal)
    return max(-1.0, min(1.0, pct_change * 10))


def calculate_ma_signal(prices, short_window=12, long_window=48):
    """
    Moving average crossover signal.
    Returns "bullish", "bearish", or "neutral".
    """
    if len(prices) < long_window:
        return "neutral"

    short_ma = sum(prices[-short_window:]) / short_window
    long_ma = sum(prices[-long_window:]) / long_window

    diff_pct = (short_ma - long_ma) / long_ma if long_ma > 0 else 0

    if diff_pct > 0.002:  # 0.2% above
        return "bullish"
    elif diff_pct < -0.002:
        return "bearish"
    return "neutral"


# =====================
# MARKET SCANNING
# =====================

def fetch_short_term_markets():
    """
    Fetch active short-term crypto markets from Gamma API.
    Looks for markets about BTC/ETH price movements in short timeframes.
    """
    try:
        # Fetch recent crypto-related markets
        params = {
            "limit": 100,
            "active": "true",
            "closed": "false",
        }
        resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
        resp.raise_for_status()
        all_markets = [_normalize_market(m) for m in resp.json()]
    except Exception as e:
        print(f"  [ERROR] Failed to fetch markets: {e}")
        return []

    short_term = []
    for m in all_markets:
        parsed = parse_short_term_market(m)
        if parsed:
            short_term.append(parsed)

    return short_term


def parse_short_term_market(market):
    """
    Parse a market to see if it's a short-term crypto price bet.
    Returns parsed dict or None if not a short-term crypto market.
    """
    title = (market.get("question") or market.get("title") or "").lower()

    # Check if it's about crypto prices
    coin = None
    if any(kw in title for kw in ["bitcoin", "btc"]):
        coin = "bitcoin"
    elif any(kw in title for kw in ["ethereum", "eth ", "ether"]):
        coin = "ethereum"

    if not coin:
        return None

    # Check for price-related content
    price_keywords = ["price", "above", "below", "exceed", "hit", "reach",
                       "higher than", "lower than", "close above", "close below",
                       "$", "usd"]
    if not any(kw in title for kw in price_keywords):
        return None

    # Detect timeframe
    timeframe = "unknown"
    if re.search(r'5.?min|5m\b', title):
        timeframe = "5m"
    elif re.search(r'15.?min|15m\b', title):
        timeframe = "15m"
    elif re.search(r'hour|1h\b|60.?min', title):
        timeframe = "1h"
    elif re.search(r'daily|today|24h|end of day', title):
        timeframe = "daily"
    elif re.search(r'week|7d', title):
        timeframe = "weekly"
    elif re.search(r'march|april|may|june|july|by\s+\w+\s+\d{1,2}', title):
        timeframe = "dated"

    # Get prices
    prices = market.get("outcomePrices", [])
    if not prices or len(prices) < 2:
        return None

    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (ValueError, TypeError):
        return None

    # Extract target price from title
    price_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*k?\b', title)
    target_price = None
    if price_match:
        val = price_match.group(1).replace(",", "")
        target_price = float(val)
        # Handle "k" suffix
        if "k" in title[price_match.end():price_match.end()+2].lower():
            target_price *= 1000

    return {
        "title": market.get("question") or market.get("title") or "",
        "coin": coin,
        "timeframe": timeframe,
        "target_price": target_price,
        "yes_price": yes_price,
        "no_price": no_price,
        "market_id": market.get("id"),
        "token_ids": market.get("clobTokenIds", []),
        "volume": float(market.get("volume", 0) or 0),
    }


# =====================
# EDGE CALCULATION
# =====================

def estimate_direction_probability(coin, price_data):
    """
    Estimate probability of price going UP using Bayesian log-odds.

    Old approach: Start at 0.50, add/subtract fixed amounts in probability space.
    Problem: Adding probabilities (0.50 + 0.05 + 0.03 = 0.58) is mathematically
    wrong for combining independent signals.

    New approach: Work in log-odds space where addition IS correct for
    combining independent evidence. This is proper Bayesian updating.

    In log-odds space:
    - 0 means 50/50 (no information)
    - Positive means evidence favors UP
    - Negative means evidence favors DOWN
    - Addition correctly combines independent signals
    """
    if not price_data or len(price_data) < 20:
        return {"up_prob": 0.50, "confidence": "none"}

    rsi = calculate_rsi(price_data)
    momentum = calculate_momentum(price_data)
    ma_signal = calculate_ma_signal(price_data)

    # Start at 50% = 0 in log-odds space
    lo = 0.0

    # RSI signal (in log-odds units)
    # 0.25 in log-odds ~ 6% probability shift near center
    if rsi is not None:
        if rsi > 70:
            lo -= 0.25   # Overbought: evidence for DOWN
        elif rsi > 60:
            lo -= 0.10
        elif rsi < 30:
            lo += 0.25   # Oversold: evidence for UP
        elif rsi < 40:
            lo += 0.10

    # Momentum signal (scaled to log-odds)
    # momentum is in [-1, 1], max contribution +/- 0.30 log-odds
    lo += momentum * 0.30

    # Moving average signal
    if ma_signal == "bullish":
        lo += 0.15
    elif ma_signal == "bearish":
        lo -= 0.15

    # Convert back to probability
    up_prob = from_log_odds(lo)

    # Safety clamp: never claim more than 15% edge either way
    up_prob = max(0.35, min(0.65, up_prob))

    # Determine confidence based on deviation from 50%
    deviation = abs(up_prob - 0.50)
    if deviation >= 0.08:
        confidence = "high"
    elif deviation >= 0.04:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "up_prob": round(up_prob, 3),
        "down_prob": round(1 - up_prob, 3),
        "confidence": confidence,
        "rsi": rsi,
        "momentum": round(momentum, 3),
        "ma_signal": ma_signal,
        "log_odds": round(lo, 3),
    }


def find_short_term_edges(markets, price_data_map):
    """
    Compare estimated probabilities to market prices.
    Returns list of opportunities with edge > min threshold.
    """
    opportunities = []

    for m in markets:
        coin = m["coin"]
        if coin not in price_data_map:
            continue

        signals = estimate_direction_probability(coin, price_data_map[coin])

        # Determine which side the market is asking about
        title_lower = m["title"].lower()
        is_up_market = any(kw in title_lower for kw in ["above", "exceed", "higher", "hit", "reach"])

        if is_up_market:
            our_prob = signals["up_prob"]
            market_prob = m["yes_price"]
        else:
            our_prob = signals["down_prob"]
            market_prob = m["yes_price"]

        edge = our_prob - market_prob

        if abs(edge) < SHORT_TERM_MIN_EDGE:
            continue

        side = "YES" if edge > 0 else "NO"
        buy_price = m["yes_price"] if side == "YES" else m["no_price"]

        opportunities.append({
            **m,
            "our_prob": round(our_prob, 3),
            "market_prob": round(market_prob, 3),
            "edge": round(edge, 3),
            "side": side,
            "buy_price": round(buy_price, 3),
            "bet_amount": SHORT_TERM_BET_SIZE,
            "signals": signals,
        })

    # Sort by edge magnitude
    opportunities.sort(key=lambda x: abs(x["edge"]), reverse=True)
    return opportunities[:SHORT_TERM_MAX_POSITIONS]


# =====================
# MAIN SCAN PIPELINE
# =====================

def scan_short_term():
    """
    Full short-term crypto scan pipeline.
    """
    print("  Fetching short-term crypto markets...")
    markets = fetch_short_term_markets()
    print(f"  Found {len(markets)} crypto price markets")

    if not markets:
        return []

    # Get price data for each coin
    print("  Fetching real-time price data...")
    current_prices = fetch_current_prices()
    price_data_map = {}

    for coin in SHORT_TERM_COINS:
        if coin in current_prices:
            history = fetch_price_history(coin)
            if history:
                price_data_map[coin] = history
                print(f"    {coin}: ${current_prices[coin]:,.2f} ({len(history)} data points)")

    if not price_data_map:
        print("  Could not fetch price data.")
        return []

    # Find edges
    print("  Calculating signals and edges...")
    opportunities = find_short_term_edges(markets, price_data_map)
    print(f"  Found {len(opportunities)} opportunities with edge > {SHORT_TERM_MIN_EDGE:.0%}")

    return opportunities


def display_short_term(opportunities, price_data_map=None):
    """Pretty print short-term crypto opportunities."""
    print(f"\n{'='*70}")
    print(f"  SHORT-TERM CRYPTO OPPORTUNITIES")
    print(f"{'='*70}")

    if not opportunities:
        print("  No short-term opportunities found right now.")
        return

    for i, opp in enumerate(opportunities, 1):
        signals = opp.get("signals", {})
        print(f"\n  #{i} {opp['coin'].upper()} | {opp['timeframe']} | Edge: {opp['edge']:+.1%}")
        print(f"     {opp['title'][:80]}")
        print(f"     Market: {opp['market_prob']:.0%} | Our est: {opp['our_prob']:.0%} | -> BUY {opp['side']} @ ${opp['buy_price']:.2f}")
        print(f"     RSI: {signals.get('rsi', '?')} | Mom: {signals.get('momentum', '?')} | MA: {signals.get('ma_signal', '?')}")
        print(f"     Volume: ${opp['volume']:,.0f} | Confidence: {signals.get('confidence', '?')}")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("SHORT-TERM CRYPTO SCANNER TEST")
    print("=" * 60)

    # Show current prices
    print("\nFetching current prices...")
    prices = fetch_current_prices()
    for coin, price in prices.items():
        print(f"  {coin}: ${price:,.2f}")

    # Show technical signals
    print("\nCalculating technical signals...")
    for coin in SHORT_TERM_COINS:
        history = fetch_price_history(coin)
        if history:
            signals = estimate_direction_probability(coin, history)
            print(f"\n  {coin.upper()}:")
            print(f"    Data points: {len(history)}")
            print(f"    RSI: {signals['rsi']}")
            print(f"    Momentum: {signals['momentum']}")
            print(f"    MA signal: {signals['ma_signal']}")
            print(f"    UP probability: {signals['up_prob']:.1%}")
            print(f"    Confidence: {signals['confidence']}")

    # Scan for opportunities
    print("\n" + "-" * 60)
    opportunities = scan_short_term()
    display_short_term(opportunities)
