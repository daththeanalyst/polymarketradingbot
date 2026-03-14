"""
Paper Trading Tracker
======================
Logs all dry-run bets to a CSV file and tracks performance over time.

Usage:
  python tracker.py                # Show current stats
  python bot.py --stats            # Show stats from main bot
"""

import csv
import os
from datetime import datetime

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "bets_log.csv")
TRACKER_FIELDS = [
    "timestamp", "strategy", "market_id", "title",
    "side", "price", "amount", "shares",
    "forecast_prob",
    "category", "conviction_tier",
    "status", "outcome", "pnl",
]


def log_bet(bet, strategy="longshot"):
    """
    Append a bet record to the CSV log.
    Creates file with headers if it does not exist.
    """
    file_exists = os.path.exists(TRACKER_FILE)

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": strategy,
        "market_id": bet.get("market_id", ""),
        "title": (bet.get("title", "") or "")[:100],
        "side": bet.get("side", "YES"),
        "price": bet.get("yes_price", 0),
        "amount": bet.get("bet_amount", 0),
        "shares": bet.get("shares", 0),
        "forecast_prob": bet.get("forecast_prob", bet.get("our_prob", bet.get("estimated_prob", ""))),
        "category": bet.get("category", ""),
        "conviction_tier": bet.get("conviction_tier", ""),
        "status": "open",
        "outcome": "",
        "pnl": "",
    }

    with open(TRACKER_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return row


def load_bets():
    """Load all tracked bets from CSV."""
    if not os.path.exists(TRACKER_FILE):
        return []

    with open(TRACKER_FILE, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def calculate_stats():
    """
    Calculate performance statistics from tracked bets.
    """
    bets = load_bets()
    if not bets:
        return None

    total_bets = len(bets)
    resolved = [b for b in bets if b.get("pnl") and b["pnl"] != ""]
    open_bets = [b for b in bets if not b.get("pnl") or b["pnl"] == ""]

    total_risked = sum(float(b.get("amount", 0)) for b in bets)

    if resolved:
        total_pnl = sum(float(b["pnl"]) for b in resolved)
        wins = [b for b in resolved if float(b["pnl"]) > 0]
        hit_rate = len(wins) / len(resolved)
    else:
        total_pnl = 0
        wins = []
        hit_rate = 0

    roi = (total_pnl / total_risked * 100) if total_risked > 0 else 0

    # Category breakdown
    categories = {}
    for b in bets:
        cat = b.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "risked": 0}
        categories[cat]["count"] += 1
        categories[cat]["risked"] += float(b.get("amount", 0))

    # Brier score calibration (measures probability estimate accuracy)
    from math_utils import brier_score

    calibration_data = []
    for b in resolved:
        fp = b.get("forecast_prob", "")
        outcome = b.get("outcome", "")
        if fp != "" and outcome != "":
            try:
                calibration_data.append((float(fp), float(outcome)))
            except (ValueError, TypeError):
                pass

    bs = brier_score(calibration_data) if calibration_data else None

    # Calibration buckets: are 70% predictions right 70% of the time?
    calibration_buckets = {}
    for fp, outcome in calibration_data:
        bucket = round(fp, 1)  # Round to nearest 10%
        if bucket not in calibration_buckets:
            calibration_buckets[bucket] = {"count": 0, "hits": 0}
        calibration_buckets[bucket]["count"] += 1
        calibration_buckets[bucket]["hits"] += outcome

    return {
        "total_bets": total_bets,
        "open_bets": len(open_bets),
        "resolved_bets": len(resolved),
        "wins": len(wins),
        "losses": len(resolved) - len(wins),
        "hit_rate": round(hit_rate, 4),
        "total_risked": round(total_risked, 2),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 1),
        "categories": categories,
        "brier_score": round(bs, 4) if bs is not None else None,
        "calibration_n": len(calibration_data),
        "calibration_buckets": calibration_buckets,
    }


def display_stats():
    """Pretty print performance stats."""
    stats = calculate_stats()
    if not stats:
        print("  No tracked bets yet. Run the bot to start logging.")
        return

    print(f"\n{'='*60}")
    print(f"  PAPER TRADING PERFORMANCE")
    print(f"{'='*60}")
    print(f"\n  Total Bets:     {stats['total_bets']}")
    print(f"  Open:           {stats['open_bets']}")
    print(f"  Resolved:       {stats['resolved_bets']}")
    print(f"  Wins / Losses:  {stats['wins']} / {stats['losses']}")
    print(f"  Hit Rate:       {stats['hit_rate']:.1%}")
    print(f"  Total Risked:   ${stats['total_risked']:.2f}")
    print(f"  Total P&L:      ${stats['total_pnl']:+.2f}")
    print(f"  ROI:            {stats['roi']:+.1f}%")

    if stats["categories"]:
        print(f"\n  --- By Category ---")
        for cat, data in sorted(stats["categories"].items()):
            print(f"    {cat}: {data['count']} bets, ${data['risked']:.2f} risked")

    # Calibration section
    if stats.get("brier_score") is not None:
        bs = stats["brier_score"]
        if bs < 0.15:
            quality = "excellent"
        elif bs < 0.20:
            quality = "good"
        elif bs < 0.25:
            quality = "fair"
        else:
            quality = "poor"
        print(f"\n  --- Calibration ---")
        print(f"  Brier Score:     {bs:.4f} ({quality})")
        print(f"  (0.0 = perfect, 0.25 = random, lower is better)")
        print(f"  Resolved bets:   {stats['calibration_n']}")

        if stats.get("calibration_buckets"):
            print(f"\n  Predicted vs Actual hit rate:")
            for bucket in sorted(stats["calibration_buckets"].keys()):
                data = stats["calibration_buckets"][bucket]
                actual = data["hits"] / data["count"] if data["count"] > 0 else 0
                print(f"    {bucket:.0%} predicted -> {actual:.0%} actual ({data['count']} bets)")

    print(f"{'='*60}")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("PAPER TRADING TRACKER")
    print("=" * 60)

    bets = load_bets()
    print(f"\nLogged bets: {len(bets)}")

    if bets:
        display_stats()
    else:
        print("No bets logged yet.")
        print(f"Log file: {TRACKER_FILE}")
        print("Run the bot to start tracking bets.")
