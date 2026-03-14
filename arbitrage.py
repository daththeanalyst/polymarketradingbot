"""
Structural Arbitrage Scanner
===============================
Finds pricing inconsistencies on Polymarket that offer guaranteed or
near-guaranteed profit regardless of outcome.

Research shows arbitrage traders extracted $40M+ from Polymarket in 2024-2025.
While speed-based arbitrage (2.7-second windows) requires infrastructure we
don't have, STRUCTURAL arbitrage (logical pricing errors) can persist for hours.

Two types:
1. Sum-to-one: YES + NO < $1.00 -> buy both, guaranteed profit
2. Logical: Related markets with inconsistent prices

Usage:
  python arbitrage.py            # Scan for arbitrage opportunities
  python bot.py --arbitrage      # Run from main bot
"""

import re
import requests
from config import (
    GAMMA_API, POLYMARKET_FEE_RATE,
    ARBITRAGE_MIN_GAP, ARBITRAGE_BET_SIZE, ARBITRAGE_MAX_POSITIONS,
)
from markets import _normalize_market


# =====================
# SUM-TO-ONE ARBITRAGE
# =====================

def scan_sum_arbitrage(markets):
    """
    Find markets where YES + NO prices don't sum to $1.00.

    If YES = $0.48 and NO = $0.49, total = $0.97.
    Buy both for $0.97, one MUST pay $1.00 -> guaranteed $0.03 profit.
    But subtract 2% fee on the winning side: net profit = $0.03 - $0.02 = $0.01.

    We only flag gaps > ARBITRAGE_MIN_GAP (2.5%) to ensure profit after fees.
    """
    opportunities = []

    for m in markets:
        prices = m.get("outcomePrices", [])
        if not prices or len(prices) < 2:
            continue

        try:
            yes_price = float(prices[0])
            no_price = float(prices[1])
        except (ValueError, TypeError):
            continue

        # Skip invalid prices
        if yes_price <= 0 or no_price <= 0:
            continue
        if yes_price >= 1.0 or no_price >= 1.0:
            continue

        total = yes_price + no_price
        gap = 1.0 - total

        # Positive gap = combined cost < $1.00 = profit opportunity
        if gap < ARBITRAGE_MIN_GAP:
            continue

        # Calculate actual profit after fees
        # Winner pays 2% fee on payout, loser loses their cost
        # Worst case: the cheaper side wins (lower payout ratio)
        cost = yes_price + no_price
        gross_payout = 1.0  # One side always pays $1
        fee = gross_payout * POLYMARKET_FEE_RATE
        net_profit = gross_payout - fee - cost
        net_profit_pct = (net_profit / cost) * 100 if cost > 0 else 0

        if net_profit <= 0:
            continue

        title = m.get("question") or m.get("title") or ""
        volume = float(m.get("volume", 0) or 0)
        token_ids = m.get("clobTokenIds", [])

        opportunities.append({
            "type": "sum_to_one",
            "title": title,
            "market_id": m.get("id", ""),
            "yes_price": yes_price,
            "no_price": no_price,
            "total_cost": round(cost, 4),
            "gap": round(gap, 4),
            "net_profit": round(net_profit, 4),
            "net_profit_pct": round(net_profit_pct, 2),
            "volume": volume,
            "token_ids": token_ids,
        })

    # Sort by profit percentage (best first)
    opportunities.sort(key=lambda x: x["net_profit_pct"], reverse=True)
    return opportunities


# =====================
# LOGICAL ARBITRAGE
# =====================

def extract_price_threshold(title):
    """
    Extract a numeric threshold from a market title.
    e.g., "Will BTC exceed $100,000?" -> 100000
          "ETH above $5,000 by June?" -> 5000
    """
    # Match dollar amounts like $100,000 or $5000 or $100K
    match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)\s*(k|K|m|M)?', title)
    if not match:
        return None

    val = float(match.group(1).replace(",", ""))
    suffix = match.group(2)
    if suffix and suffix.lower() == "k":
        val *= 1000
    elif suffix and suffix.lower() == "m":
        val *= 1000000

    return val


def find_related_markets(markets):
    """
    Group markets that are about the same underlying event.
    e.g., "BTC > $80K", "BTC > $100K", "BTC > $150K" are related.

    Returns dict: {group_key: [markets]}
    """
    groups = {}

    for m in markets:
        title = (m.get("question") or m.get("title") or "").lower()
        prices = m.get("outcomePrices", [])
        if not prices or len(prices) < 2:
            continue

        try:
            yes_price = float(prices[0])
        except (ValueError, TypeError):
            continue

        threshold = extract_price_threshold(title)
        if threshold is None:
            continue

        # Determine the subject (BTC, ETH, etc.)
        subject = None
        if any(kw in title for kw in ["bitcoin", "btc"]):
            subject = "bitcoin"
        elif any(kw in title for kw in ["ethereum", " eth ", "ether"]):
            subject = "ethereum"
        elif any(kw in title for kw in ["s&p", "sp500", "s&p 500"]):
            subject = "sp500"

        if not subject:
            continue

        # Determine direction
        is_above = any(kw in title for kw in ["above", "exceed", "higher", "hit", "reach", "over"])

        if not is_above:
            continue  # Only track "above" markets for now

        group_key = f"{subject}_above"
        if group_key not in groups:
            groups[group_key] = []

        groups[group_key].append({
            "title": m.get("question") or m.get("title") or "",
            "market_id": m.get("id", ""),
            "threshold": threshold,
            "yes_price": yes_price,
            "volume": float(m.get("volume", 0) or 0),
            "token_ids": m.get("clobTokenIds", []),
        })

    # Sort each group by threshold ascending
    for key in groups:
        groups[key].sort(key=lambda x: x["threshold"])

    return groups


def scan_logical_arbitrage(markets):
    """
    Find logical pricing inconsistencies between related markets.

    Key rule: If threshold_A < threshold_B, then P(above A) >= P(above B).
    e.g., P(BTC > $80K) MUST be >= P(BTC > $100K).

    If the market prices violate this, there's an arbitrage:
    Buy YES on the lower threshold, sell YES on the higher threshold.
    """
    groups = find_related_markets(markets)
    opportunities = []

    for group_key, group_markets in groups.items():
        if len(group_markets) < 2:
            continue

        # Check all pairs for violations
        for i in range(len(group_markets)):
            for j in range(i + 1, len(group_markets)):
                lower = group_markets[i]  # Lower threshold
                higher = group_markets[j]  # Higher threshold

                # lower threshold should have HIGHER or EQUAL yes_price
                if lower["yes_price"] < higher["yes_price"]:
                    # VIOLATION: cheaper threshold is priced lower
                    mispricing = higher["yes_price"] - lower["yes_price"]

                    if mispricing < ARBITRAGE_MIN_GAP:
                        continue

                    opportunities.append({
                        "type": "logical",
                        "group": group_key,
                        "buy_market": lower["title"],
                        "buy_price": lower["yes_price"],
                        "buy_threshold": lower["threshold"],
                        "buy_token_ids": lower["token_ids"],
                        "sell_market": higher["title"],
                        "sell_price": higher["yes_price"],
                        "sell_threshold": higher["threshold"],
                        "sell_token_ids": higher["token_ids"],
                        "mispricing": round(mispricing, 4),
                        "mispricing_pct": round(mispricing * 100, 2),
                    })

    opportunities.sort(key=lambda x: x["mispricing"], reverse=True)
    return opportunities


# =====================
# FULL SCAN PIPELINE
# =====================

def fetch_all_for_arbitrage(max_pages=5):
    """Fetch markets from Gamma API for arbitrage scanning."""
    all_markets = []
    try:
        for page in range(max_pages):
            params = {
                "limit": 100,
                "offset": page * 100,
                "active": "true",
                "closed": "false",
            }
            resp = requests.get(f"{GAMMA_API}/markets", params=params, timeout=15)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_markets.extend([_normalize_market(m) for m in batch])
    except Exception as e:
        print(f"  [ERROR] Failed to fetch markets: {e}")

    return all_markets


def scan_arbitrage():
    """Full arbitrage scan pipeline."""
    print("  Fetching markets for arbitrage scan...")
    markets = fetch_all_for_arbitrage(max_pages=5)
    print(f"  Scanning {len(markets)} markets...")

    # Sum-to-one arbitrage
    sum_opps = scan_sum_arbitrage(markets)
    print(f"  Sum-to-one opportunities: {len(sum_opps)}")

    # Logical arbitrage
    logical_opps = scan_logical_arbitrage(markets)
    print(f"  Logical arbitrage opportunities: {len(logical_opps)}")

    return {
        "sum_to_one": sum_opps,
        "logical": logical_opps,
        "total": len(sum_opps) + len(logical_opps),
    }


def display_arbitrage(results):
    """Pretty print arbitrage opportunities."""
    print(f"\n{'='*70}")
    print(f"  STRUCTURAL ARBITRAGE SCANNER")
    print(f"{'='*70}")

    # Sum-to-one
    sum_opps = results.get("sum_to_one", [])
    if sum_opps:
        print(f"\n  --- SUM-TO-ONE ARBITRAGE ({len(sum_opps)} found) ---")
        print(f"  (Buy YES + NO for less than $1.00 = guaranteed profit)")
        for i, opp in enumerate(sum_opps[:5], 1):
            print(f"\n  #{i} Gap: {opp['gap']*100:.1f}c | Net profit: ${opp['net_profit']:.4f} ({opp['net_profit_pct']:+.2f}%)")
            print(f"     {opp['title'][:75]}")
            print(f"     YES: ${opp['yes_price']:.3f} + NO: ${opp['no_price']:.3f} = ${opp['total_cost']:.3f}")
            print(f"     Volume: ${opp['volume']:,.0f}")
    else:
        print(f"\n  No sum-to-one arbitrage found (all markets sum to ~$1.00)")

    # Logical
    logical_opps = results.get("logical", [])
    if logical_opps:
        print(f"\n  --- LOGICAL ARBITRAGE ({len(logical_opps)} found) ---")
        print(f"  (Related markets with inconsistent pricing)")
        for i, opp in enumerate(logical_opps[:5], 1):
            print(f"\n  #{i} Mispricing: {opp['mispricing_pct']:.1f}% | Group: {opp['group']}")
            print(f"     BUY:  {opp['buy_market'][:60]}")
            print(f"           Threshold: ${opp['buy_threshold']:,.0f} | Price: {opp['buy_price']*100:.1f}c")
            print(f"     SELL: {opp['sell_market'][:60]}")
            print(f"           Threshold: ${opp['sell_threshold']:,.0f} | Price: {opp['sell_price']*100:.1f}c")
    else:
        print(f"\n  No logical arbitrage found (related markets are consistently priced)")

    total = results.get("total", 0)
    if total == 0:
        print(f"\n  Markets are efficiently priced right now. Check back later.")
    else:
        print(f"\n  Total opportunities: {total}")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("STRUCTURAL ARBITRAGE SCANNER")
    print("=" * 60)

    results = scan_arbitrage()
    display_arbitrage(results)
