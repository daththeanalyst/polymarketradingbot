"""
High-Probability Farming Strategy
====================================
Scans for markets priced 90-99c where the outcome is nearly certain.
Buy YES, wait for resolution, collect small but consistent profits.

This is how top Polymarket bots auto-compound thousands of micro-trades.
The #1 earner (LucasMeow) made $243K with 94.9% win rate using this approach.

Example:
  Market "Did BTC close above $60K on March 12?" -- BTC closed at $71K.
  Market is at 96c but hasn't resolved yet.
  Buy YES at 96c -> collect $1.00 per share -> 4.2% return in hours.

Usage:
  python high_prob.py            # Scan for high-prob opportunities
  python bot.py --high-prob      # Run from main bot
"""

import requests
from config import (
    GAMMA_API, POLYMARKET_FEE_RATE,
    HIGH_PROB_MIN_PRICE, HIGH_PROB_MIN_VOLUME,
    HIGH_PROB_BET_SIZE, HIGH_PROB_MAX_POSITIONS,
)
from markets import _normalize_market
from math_utils import ev_with_fees


# =====================
# MARKET SCANNING
# =====================

def fetch_high_prob_markets():
    """
    Fetch active markets and filter for high-probability candidates.
    Looks for markets with YES price >= 90c and decent volume.
    """
    try:
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

    candidates = []
    for m in all_markets:
        parsed = parse_high_prob(m)
        if parsed:
            candidates.append(parsed)

    # Sort by price descending (highest probability first)
    candidates.sort(key=lambda x: x["yes_price"], reverse=True)
    return candidates


def parse_high_prob(market):
    """
    Check if a market qualifies for high-probability farming.
    Returns parsed dict or None if it doesn't qualify.
    """
    prices = market.get("outcomePrices", [])
    if not prices or len(prices) < 2:
        return None

    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (ValueError, TypeError):
        return None

    # Filter: YES price must be >= threshold (e.g., 90c)
    if yes_price < HIGH_PROB_MIN_PRICE:
        return None

    # Filter: Must have decent volume (skip dead/illiquid markets)
    volume = float(market.get("volume", 0) or 0)
    if volume < HIGH_PROB_MIN_VOLUME:
        return None

    # Filter: Skip markets that are too close to 100% (no profit after fees)
    # At 99c: return = 1.02% gross, minus 2% fee = -0.98% net -> SKIP
    # At 98c: return = 2.04% gross, minus 2% fee = +0.04% net -> MARGINAL
    # At 97c: return = 3.09% gross, minus 2% fee = +1.09% net -> OK
    max_price = 1.0 - POLYMARKET_FEE_RATE - 0.005  # Leave room for fee + buffer
    if yes_price > max_price:
        return None

    title = market.get("question") or market.get("title") or ""
    token_ids = market.get("clobTokenIds", [])

    # Calculate return if YES wins
    shares_per_dollar = 1.0 / yes_price
    gross_payout = shares_per_dollar * 1.0
    net_payout = gross_payout * (1.0 - POLYMARKET_FEE_RATE)
    net_return_pct = (net_payout - 1.0) * 100  # % return on investment

    return {
        "title": title,
        "market_id": market.get("id", ""),
        "yes_price": yes_price,
        "no_price": no_price,
        "volume": volume,
        "token_ids": token_ids,
        "net_return_pct": round(net_return_pct, 2),
        "shares_per_dollar": round(shares_per_dollar, 2),
        "end_date": market.get("endDate", ""),
    }


# =====================
# EVALUATION
# =====================

def evaluate_high_prob(market, estimated_prob=None):
    """
    Evaluate a high-probability market.

    For markets at 95c+, we assume estimated_prob = yes_price + small edge.
    The key question is: are we MORE confident than the market?

    Conservative approach: only bet if we estimate prob > price + fee margin.
    """
    price = market["yes_price"]

    if estimated_prob is None:
        # Default: assume we're 1-2% more confident than market
        # This is conservative -- we only bet on near-certainties
        estimated_prob = min(price + 0.015, 0.995)

    bet_amount = HIGH_PROB_BET_SIZE
    ev = ev_with_fees(estimated_prob, price, bet_amount, POLYMARKET_FEE_RATE)

    return {
        **market,
        "estimated_prob": round(estimated_prob, 4),
        "bet_amount": bet_amount,
        "ev": round(ev, 4),
        "ev_positive": ev > 0,
    }


# =====================
# PORTFOLIO BUILDER
# =====================

def build_high_prob_portfolio(candidates, bankroll):
    """
    Build a portfolio of high-probability bets within budget.
    Spreads risk across multiple near-certain outcomes.
    """
    portfolio = []
    remaining = bankroll

    for market in candidates:
        if len(portfolio) >= HIGH_PROB_MAX_POSITIONS:
            break
        if remaining < HIGH_PROB_BET_SIZE:
            break

        evaluated = evaluate_high_prob(market)

        if evaluated["ev_positive"]:
            portfolio.append(evaluated)
            remaining -= evaluated["bet_amount"]

    return portfolio


# =====================
# SCAN PIPELINE
# =====================

def scan_high_prob():
    """Full high-probability farming scan pipeline."""
    print("  Fetching markets for high-probability farming...")
    candidates = fetch_high_prob_markets()
    print(f"  Found {len(candidates)} markets at {HIGH_PROB_MIN_PRICE*100:.0f}c+ with volume >= ${HIGH_PROB_MIN_VOLUME:,.0f}")

    if not candidates:
        return []

    # Evaluate all candidates
    evaluated = []
    for c in candidates:
        ev = evaluate_high_prob(c)
        if ev["ev_positive"]:
            evaluated.append(ev)

    print(f"  {len(evaluated)} have positive EV after 2% fee")
    return evaluated


def display_high_prob(opportunities):
    """Pretty print high-probability farming opportunities."""
    print(f"\n{'='*70}")
    print(f"  HIGH-PROBABILITY FARMING OPPORTUNITIES")
    print(f"{'='*70}")

    if not opportunities:
        print("  No high-prob opportunities found right now.")
        return

    total_cost = 0
    total_potential_profit = 0

    for i, opp in enumerate(opportunities[:15], 1):
        ret = opp["net_return_pct"]
        print(f"\n  #{i} [{opp['yes_price']*100:.1f}c] +{ret:.1f}% net | Vol: ${opp['volume']:,.0f}")
        print(f"     {opp['title'][:80]}")
        print(f"     EV: ${opp['ev']:+.4f} per ${opp['bet_amount']:.2f} bet")

        total_cost += opp["bet_amount"]
        total_potential_profit += opp["ev"]

    if len(opportunities) > 15:
        print(f"\n  ... and {len(opportunities) - 15} more")

    print(f"\n  Portfolio: {min(len(opportunities), HIGH_PROB_MAX_POSITIONS)} bets")
    print(f"  Total cost: ${total_cost:.2f}")
    print(f"  Expected profit: ${total_potential_profit:.4f}")
    if total_cost > 0:
        print(f"  Expected ROI: {total_potential_profit/total_cost*100:+.2f}%")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("HIGH-PROBABILITY FARMING SCANNER")
    print("=" * 60)

    opportunities = scan_high_prob()
    display_high_prob(opportunities)

    if opportunities:
        print(f"\n  To auto-bet, run: python bot.py --high-prob")
