"""
Long Shot Scanner
==================
Finds low-probability markets (<=5c) with massive multipliers (20x-100x+)
that are logically plausible — not fantasy.

The idea: bet $0.50 on something at 2c = 25 shares.
If it hits: 25 x $1 = $25 (50x return).
Most will lose, but one hit covers many losses.
"""

from config import (
    LONGSHOT_MAX_PRICE, LONGSHOT_MIN_VOLUME,
    LONGSHOT_EXCLUDE_KEYWORDS, LONGSHOT_TOP_PICKS,
    CATEGORY_SCORES, CATEGORY_KEYWORDS,
)
from markets import fetch_all_markets


def find_longshots(all_markets, max_price=None):
    """
    Find all markets where YES is priced at max_price or less.
    These are the "long shot" candidates.
    """
    if max_price is None:
        max_price = LONGSHOT_MAX_PRICE

    longshots = []

    for m in all_markets:
        prices = m.get("outcomePrices", [])
        if not prices:
            continue

        try:
            yes_price = float(prices[0])
        except (ValueError, TypeError):
            continue

        if yes_price <= 0 or yes_price > max_price:
            continue

        title = m.get("question") or m.get("title") or ""
        volume = float(m.get("volume", 0) or 0)

        longshots.append({
            "title": title,
            "yes_price": yes_price,
            "no_price": float(prices[1]) if len(prices) > 1 else 1 - yes_price,
            "multiplier": round(1 / yes_price, 1),
            "volume": volume,
            "market_id": m.get("id"),
            "token_ids": m.get("clobTokenIds", []),
            "outcomes": m.get("outcomes", []),
            "end_date": m.get("endDate"),
            "tags": [t.get("label", "") for t in m.get("tags", [])],
        })

    return longshots


def classify_category(longshot):
    """
    Classify a longshot into a category based on title and tag keywords.
    Returns the category key (e.g., "crypto_milestone") or "general".
    """
    title_lower = longshot["title"].lower()
    tags_lower = " ".join([t.lower() for t in longshot.get("tags", [])])
    # Pad with spaces so keywords like " eth " match word boundaries
    combined = " " + title_lower + " " + tags_lower + " "

    best_category = "general"
    best_match_count = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in combined)
        if match_count > best_match_count:
            best_match_count = match_count
            best_category = category

    return best_category


def is_logical(longshot):
    """
    Filter out fantasy/impossible events AND overpriced categories.
    Returns True if the long shot is logically plausible and worth considering.
    """
    title_lower = longshot["title"].lower()

    # Exclude fantasy/impossible events
    for keyword in LONGSHOT_EXCLUDE_KEYWORDS:
        if keyword.lower() in title_lower:
            return False

    # Reject categories that are systematically overpriced
    category = classify_category(longshot)
    if CATEGORY_SCORES.get(category, 0) <= -15:
        return False

    return True


def score_longshot(longshot):
    """
    Score a long shot by how "good" it is as a bet.
    Higher score = better candidate.

    Factors:
    - Volume (market legitimacy)
    - Multiplier sweet spot (20x-50x)
    - Category score (underpriced vs overpriced based on research)
    - Dead market penalty
    """
    score = 0.0

    # Volume score (log scale)
    vol = longshot["volume"]
    if vol >= 100000:
        score += 30
    elif vol >= 50000:
        score += 25
    elif vol >= 10000:
        score += 20
    elif vol >= 5000:
        score += 15
    elif vol >= 1000:
        score += 10
    elif vol >= 100:
        score += 5

    # Multiplier score (sweet spot: 20x-50x)
    mult = longshot["multiplier"]
    if 20 <= mult <= 50:
        score += 20
    elif 50 < mult <= 100:
        score += 15
    elif mult > 100:
        score += 10
    else:
        score += 5

    # Category-based scoring (replaces flat +10 bonus)
    category = classify_category(longshot)
    category_adjustment = CATEGORY_SCORES.get(category, 0)
    score += category_adjustment

    # Penalty for very low volume
    if vol < LONGSHOT_MIN_VOLUME:
        score -= 15

    longshot["score"] = score
    longshot["category"] = category
    return longshot


def filter_logical(longshots):
    """Remove fantasy/impossible markets."""
    return [ls for ls in longshots if is_logical(ls)]


def rank_best_longshots(longshots, top_n=None):
    """
    Score and rank long shots, return top N.
    """
    if top_n is None:
        top_n = LONGSHOT_TOP_PICKS

    # Filter out fantasy
    logical = filter_logical(longshots)

    # Filter out dead markets
    active = [ls for ls in logical if ls["volume"] >= LONGSHOT_MIN_VOLUME]

    # Score each one
    scored = [score_longshot(ls) for ls in active]

    # Sort by score (highest first)
    scored.sort(key=lambda x: x["score"], reverse=True)

    return scored[:top_n]


def scan_longshots(all_markets=None):
    """
    Full long shot scan pipeline.
    Returns ranked list of best long shot opportunities.
    """
    if all_markets is None:
        print("  Fetching all markets for long shot scan...")
        all_markets = fetch_all_markets(max_pages=10)

    print(f"  Scanning {len(all_markets)} markets for long shots (<={LONGSHOT_MAX_PRICE*100:.0f}c)...")

    # Find candidates
    candidates = find_longshots(all_markets)
    print(f"  Found {len(candidates)} markets priced <={LONGSHOT_MAX_PRICE*100:.0f}c")

    # Filter logical ones
    logical = filter_logical(candidates)
    print(f"  {len(logical)} passed logical filter (removed fantasy/impossible)")

    # Rank them
    ranked = rank_best_longshots(logical)
    print(f"  Top {len(ranked)} long shots selected")

    return ranked


def display_longshots(longshots):
    """Pretty print long shot opportunities."""
    print(f"\n{'='*70}")
    print(f"  TOP LONG SHOT OPPORTUNITIES")
    print(f"{'='*70}")

    for i, ls in enumerate(longshots, 1):
        bet_amount = ls.get("bet_amount", 0.50)
        shares = bet_amount / ls["yes_price"]
        potential_payout = shares * 1.0
        category = ls.get("category", "?")
        tier = ls.get("conviction_tier", "?")

        print(f"\n  #{i} [{ls['yes_price']*100:.1f}c] x{ls['multiplier']} | Score: {ls['score']:.0f} | {category}")
        print(f"     {ls['title'][:80]}")
        print(f"     Volume: ${ls['volume']:,.0f} | Tier: {tier} (${bet_amount:.2f})")
        print(f"     ${bet_amount:.2f} bet -> {shares:.0f} shares -> ${potential_payout:.2f} if YES")

    if not longshots:
        print("  No long shots found matching criteria.")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("LONG SHOT SCANNER TEST")
    print("=" * 60)

    ranked = scan_longshots()
    display_longshots(ranked)

    print(f"\n--- ALL CANDIDATES (unranked) ---")
    all_markets = fetch_all_markets(max_pages=10)
    all_longshots = find_longshots(all_markets)
    logical = filter_logical(all_longshots)

    print(f"\nTotal long shot candidates: {len(all_longshots)}")
    print(f"Passed logical filter: {len(logical)}")
    print(f"With sufficient volume: {len([l for l in logical if l['volume'] >= LONGSHOT_MIN_VOLUME])}")
