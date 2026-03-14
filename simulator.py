"""
Monte Carlo Simulator
======================
Simulates long shot portfolio outcomes using Monte Carlo method.
Runs N scenarios of binary outcomes to estimate:
- Probability of profit
- Expected return / ROI
- Best / worst / median outcomes

Usage:
  python simulator.py              # Simulate example portfolio
  python bot.py --simulate         # Simulate current live portfolio
"""

import random


def simulate_portfolio(bets, num_simulations=10000):
    """
    Run Monte Carlo simulation on a portfolio of binary bets.

    Each bet needs:
    - bet_amount: dollars risked
    - estimated_prob: our estimated probability of YES
    - payout_if_yes: dollars received if YES wins
    """
    results = []

    for _ in range(num_simulations):
        portfolio_pnl = 0.0

        for bet in bets:
            prob = bet["estimated_prob"]
            cost = bet["bet_amount"]
            payout = bet["payout_if_yes"]

            if random.random() < prob:
                portfolio_pnl += (payout - cost)  # Win
            else:
                portfolio_pnl -= cost              # Lose

        results.append(portfolio_pnl)

    results.sort()
    return analyze_results(results, bets)


def analyze_results(results, bets):
    """Compute summary statistics from simulation results."""
    n = len(results)
    total_cost = sum(b["bet_amount"] for b in bets)

    profitable = sum(1 for r in results if r > 0)

    return {
        "num_simulations": n,
        "num_bets": len(bets),
        "total_cost": round(total_cost, 2),
        "prob_profit": round(profitable / n, 4),
        "expected_return": round(sum(results) / n, 2),
        "expected_roi": round((sum(results) / n) / total_cost * 100, 1) if total_cost > 0 else 0,
        "median_return": round(results[n // 2], 2),
        "best_case": round(results[-1], 2),
        "worst_case": round(results[0], 2),
        "percentile_5": round(results[int(n * 0.05)], 2),
        "percentile_25": round(results[int(n * 0.25)], 2),
        "percentile_75": round(results[int(n * 0.75)], 2),
        "percentile_95": round(results[int(n * 0.95)], 2),
        "results_raw": results,
    }


def display_simulation(sim):
    """Pretty print simulation results."""
    print(f"\n{'='*60}")
    print(f"  MONTE CARLO SIMULATION RESULTS")
    print(f"  ({sim['num_simulations']:,} scenarios, {sim['num_bets']} bets)")
    print(f"{'='*60}")

    print(f"\n  Total Risked:        ${sim['total_cost']:.2f}")
    print(f"  Probability Profit:  {sim['prob_profit']:.1%}")
    print(f"  Expected Return:     ${sim['expected_return']:+.2f}")
    print(f"  Expected ROI:        {sim['expected_roi']:+.1f}%")

    print(f"\n  --- Return Distribution ---")
    print(f"  Worst case (0th):    ${sim['worst_case']:+.2f}")
    print(f"  5th percentile:      ${sim['percentile_5']:+.2f}")
    print(f"  25th percentile:     ${sim['percentile_25']:+.2f}")
    print(f"  Median (50th):       ${sim['median_return']:+.2f}")
    print(f"  75th percentile:     ${sim['percentile_75']:+.2f}")
    print(f"  95th percentile:     ${sim['percentile_95']:+.2f}")
    print(f"  Best case (100th):   ${sim['best_case']:+.2f}")
    print(f"{'='*60}")


def display_histogram(results, bins=15):
    """Print ASCII histogram of return distribution."""
    min_val = min(results)
    max_val = max(results)

    if max_val == min_val:
        print("\n  All outcomes identical -- no histogram to show.")
        return

    bin_width = (max_val - min_val) / bins

    # Count occurrences in each bin
    counts = [0] * bins
    for r in results:
        idx = min(int((r - min_val) / bin_width), bins - 1)
        counts[idx] += 1

    max_count = max(counts)
    bar_max_width = 35

    print(f"\n  --- Return Histogram ---")
    for i in range(bins):
        low = min_val + i * bin_width
        bar_len = int(counts[i] / max_count * bar_max_width) if max_count > 0 else 0
        bar = "#" * bar_len
        marker = " <-- break even" if low <= 0 < low + bin_width else ""
        print(f"  ${low:+8.2f} |{bar}{marker}")
    print()


def calc_at_least_one_hit(probs):
    """
    Calculate probability of at least 1 bet hitting.
    P(at least 1) = 1 - P(all miss) = 1 - prod(1 - p_i)
    """
    all_miss = 1.0
    for p in probs:
        all_miss *= (1 - p)
    return 1 - all_miss


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("MONTE CARLO SIMULATOR TEST")
    print("=" * 60)

    # Example portfolio matching current bot output
    test_portfolio = [
        {"title": "Bitcoin $150k by June", "bet_amount": 1.50, "estimated_prob": 0.06, "payout_if_yes": 50.00, "yes_price": 0.03},
        {"title": "Russia-Ukraine ceasefire", "bet_amount": 1.50, "estimated_prob": 0.06, "payout_if_yes": 73.17, "yes_price": 0.021},
        {"title": "OpenAI hardware product", "bet_amount": 1.50, "estimated_prob": 0.06, "payout_if_yes": 68.18, "yes_price": 0.022},
        {"title": "Bitcoin $150k by March", "bet_amount": 1.50, "estimated_prob": 0.02, "payout_if_yes": 230.77, "yes_price": 0.007},
        {"title": "OpenAI IPO market cap", "bet_amount": 1.50, "estimated_prob": 0.10, "payout_if_yes": 43.48, "yes_price": 0.035},
        {"title": "GTA VI before June", "bet_amount": 1.50, "estimated_prob": 0.06, "payout_if_yes": 54.55, "yes_price": 0.028},
        {"title": "Jokic NBA MVP", "bet_amount": 1.50, "estimated_prob": 0.10, "payout_if_yes": 31.58, "yes_price": 0.048},
    ]

    print(f"\nPortfolio: {len(test_portfolio)} bets")
    total = sum(b["bet_amount"] for b in test_portfolio)
    print(f"Total risked: ${total:.2f}")

    # Prob of at least 1 hit
    probs = [b["estimated_prob"] for b in test_portfolio]
    p_hit = calc_at_least_one_hit(probs)
    print(f"P(at least 1 hit): {p_hit:.1%}")

    # Run simulation
    print(f"\nRunning 10,000 simulations...")
    sim = simulate_portfolio(test_portfolio, num_simulations=10000)
    display_simulation(sim)
    display_histogram(sim["results_raw"])
