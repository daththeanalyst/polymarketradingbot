"""
Math Utilities for Polymarket Bot
===================================
Core mathematical functions used across all strategies.
All formulas are proven, well-documented, and use only stdlib (math module).

Functions:
  normal_cdf      - Probability from normal distribution (replaces hardcoded lookup)
  log_odds        - Convert probability to log-odds for Bayesian signal combination
  from_log_odds   - Convert log-odds back to probability
  kelly_fraction  - Optimal bet fraction for binary markets (Kelly Criterion)
  position_size   - Dollar amount from fractional Kelly
  ev_with_fees    - Expected value including Polymarket's 2% fee
  bayesian_update - Update probability with new evidence (Bayes' theorem)
  brier_score     - Measure how accurate your probability estimates are
"""

from math import erf, sqrt, log, exp


# =====================
# PROBABILITY FUNCTIONS
# =====================

def normal_cdf(x, mean=0.0, sigma=1.0):
    """
    Cumulative distribution function for the normal distribution.
    Returns P(X <= x) where X ~ Normal(mean, sigma^2).

    This replaces the old 10-step hardcoded lookup table.
    Instead of cliff-edge jumps (4.9F=75%, 5.0F=85%), this gives
    smooth, continuous probabilities grounded in statistics.

    Uses Python's built-in math.erf (error function). No numpy needed.

    Example:
      normal_cdf(72, mean=78, sigma=2.0) = P(temp <= 72 when forecast is 78)
      = 0.0013 (very unlikely to be that cold)
    """
    if sigma <= 0:
        return 1.0 if x >= mean else 0.0
    z = (x - mean) / (sigma * sqrt(2))
    return 0.5 * (1.0 + erf(z))


def log_odds(p):
    """
    Convert probability to log-odds space.

    Why log-odds? When combining independent signals (RSI, momentum, MA),
    you should ADD in log-odds space, not in probability space.

    Adding probabilities: 0.50 + 0.05 + 0.03 = 0.58 (WRONG - not mathematically valid)
    Adding log-odds: 0.0 + 0.20 + 0.12 -> convert back = 0.58 (CORRECT Bayesian update)

    The numbers look similar near 50%, but diverge at extremes where it matters most.

    log_odds(0.50) = 0.0   (no information)
    log_odds(0.75) = 1.10  (favoring YES)
    log_odds(0.25) = -1.10 (favoring NO)
    """
    p = max(1e-9, min(1.0 - 1e-9, p))
    return log(p / (1.0 - p))


def from_log_odds(lo):
    """
    Convert log-odds back to probability (inverse logistic / sigmoid).

    from_log_odds(0.0)  = 0.50 (50/50)
    from_log_odds(1.10) = 0.75
    from_log_odds(-1.10) = 0.25
    """
    # Guard against overflow
    if lo > 30:
        return 1.0 - 1e-9
    if lo < -30:
        return 1e-9
    return 1.0 / (1.0 + exp(-lo))


# =====================
# KELLY CRITERION
# =====================

def kelly_fraction(p, price, fee_rate=0.02):
    """
    Kelly Criterion for a Polymarket binary bet.

    The Kelly Criterion is mathematically proven to maximize long-term
    wealth growth rate. It tells you WHAT FRACTION of your bankroll to bet.

    For a YES bet at price `price`:
      If YES wins: you get (1 - fee_rate) per share, you paid `price` per share
      Net win per share  = (1 - fee_rate) - price
      Net loss per share = price

      b = net_win / net_loss  (the "odds" you're getting)
      f* = (p * b - q) / b   (Kelly fraction)
      where q = 1 - p

    Args:
        p: Your estimated probability of YES winning (0 to 1)
        price: Market price per share (e.g., 0.35 = 35 cents)
        fee_rate: Polymarket fee on winnings (default 2%)

    Returns:
        Optimal fraction of bankroll to bet. 0 if no edge.

    Example:
        You think YES is 60% likely, market says 40 cents:
        kelly_fraction(0.60, 0.40) = 0.367 (bet 36.7% of bankroll)
        But we use QUARTER Kelly (see position_size), so 0.367 * 0.25 = 9.2%
    """
    if price <= 0 or price >= 1.0:
        return 0.0

    net_payout = 1.0 - fee_rate  # What you collect per share on a win
    net_win = net_payout - price  # Profit per share if correct
    net_loss = price              # Loss per share if wrong

    if net_win <= 0:
        return 0.0  # Can't profit even if we're right (price too high)

    b = net_win / net_loss  # Net odds
    q = 1.0 - p

    f_star = (p * b - q) / b

    return max(0.0, f_star)


def position_size(p, price, bankroll, fraction=0.25, fee_rate=0.02, max_pct=0.05):
    """
    Calculate dollar amount to bet using fractional Kelly.

    Full Kelly maximizes growth but has huge variance. Quarter Kelly (0.25)
    achieves ~75% of the growth rate with MUCH less risk of ruin.
    This is what professional bettors use.

    Args:
        p: Estimated probability of winning
        price: Market price you're buying at
        bankroll: Available bankroll in dollars
        fraction: Kelly fraction (0.25 = quarter Kelly, safest for beginners)
        fee_rate: Polymarket fee rate
        max_pct: Safety cap - never bet more than this % of bankroll

    Returns:
        Dollar amount to bet

    Example:
        p=0.60, price=0.40, bankroll=$50, fraction=0.25
        kelly = 0.367, quarter = 0.092, bet = $4.59
        But max_pct=0.05 caps it at $2.50
    """
    f = kelly_fraction(p, price, fee_rate)
    size = f * fraction * bankroll

    # Safety cap
    max_bet = bankroll * max_pct
    return min(size, max_bet)


# =====================
# EXPECTED VALUE
# =====================

def ev_with_fees(p, price, bet_amount, fee_rate=0.02):
    """
    Expected value of a binary bet INCLUDING Polymarket's fee.

    Old formula: EV = (p * payout) - ((1-p) * bet)
    This formula: EV = (p * payout * (1-fee)) - bet_amount

    The fee matters! For a 3-cent longshot with $0.50 bet:
      Without fee: EV = 0.06 * $16.67 - $0.50 = +$0.50
      With 2% fee: EV = 0.06 * $16.33 - $0.50 = +$0.48
    Small difference here, but for marginal bets it determines +EV vs -EV.

    Args:
        p: Estimated probability of winning
        price: Price per share
        bet_amount: Dollar amount being bet
        fee_rate: Fee on winnings (default 2%)

    Returns:
        Expected dollar profit (positive = good bet, negative = bad bet)
    """
    if price <= 0:
        return 0.0

    shares = bet_amount / price
    gross_payout = shares * 1.0           # Each share pays $1 if YES
    net_payout = gross_payout * (1.0 - fee_rate)  # Minus fee

    # EV = P(win) * profit_if_win - P(lose) * loss_if_lose
    # profit_if_win = net_payout - bet_amount
    # loss_if_lose = bet_amount
    ev = (p * net_payout) - bet_amount
    return ev


# =====================
# BAYESIAN UPDATING
# =====================

def bayesian_update(prior, likelihood_ratio):
    """
    Update a probability using Bayes' theorem.

    Instead of guessing "real probability = market_price * 2.5",
    this uses the market price as a PRIOR (what the crowd thinks)
    and adjusts it based on your evidence (the likelihood ratio).

    The market is usually right. We only adjust at the margin where
    we have specific knowledge (e.g., category analysis shows crypto
    milestones are systematically underpriced).

    Args:
        prior: Starting probability (e.g., market price = 0.03)
        likelihood_ratio: How much more likely is the evidence
                          under "YES happens" vs "NO happens".
                          LR > 1 = evidence supports YES
                          LR < 1 = evidence supports NO
                          LR = 1 = evidence is neutral

    Returns:
        Posterior (updated) probability

    Example:
        Market says 3% chance of Bitcoin $150k. Category analysis
        says crypto milestones are 2x underpriced (LR=2.0):
        bayesian_update(0.03, 2.0) = 0.058 (about 6%)

        This is more principled than "0.03 * 2.0 = 0.06" because
        Bayes' theorem correctly handles the base rate.
    """
    prior = max(1e-9, min(1.0 - 1e-9, prior))
    numerator = prior * likelihood_ratio
    posterior = numerator / (numerator + (1.0 - prior))
    return max(1e-9, min(1.0 - 1e-9, posterior))


# =====================
# CALIBRATION
# =====================

def brier_score(forecasts_and_outcomes):
    """
    Brier score -- measures how accurate your probability estimates are.

    Lower is better:
      0.00 = perfect (you predicted 100% and it happened, every time)
      0.25 = coin flip (random guessing)
      > 0.25 = worse than random (your model is miscalibrated)

    After 50+ resolved bets, this tells you whether to trust the bot.
    Professional forecasters on Metaculus average around 0.15-0.20.

    Args:
        forecasts_and_outcomes: list of (forecast_prob, actual_outcome)
            forecast_prob: what you predicted (0.0 to 1.0)
            actual_outcome: what happened (0 or 1)

    Returns:
        Brier score (float), or None if no data

    Example:
        You predicted 70% and it happened (1): penalty = (0.7 - 1)^2 = 0.09
        You predicted 70% and it didn't (0):  penalty = (0.7 - 0)^2 = 0.49
        Average over many predictions = your Brier score
    """
    if not forecasts_and_outcomes:
        return None

    n = len(forecasts_and_outcomes)
    total = sum((f - o) ** 2 for f, o in forecasts_and_outcomes)
    return total / n


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("MATH UTILS - UNIT TESTS")
    print("=" * 60)

    # Test 1: Normal CDF
    print("\n--- Normal CDF ---")
    tests = [
        (78, 72, 2.0, "above", "Forecast 78F, threshold 72F, sigma 2 (1-day)"),
        (73, 72, 2.0, "above", "Forecast 73F, threshold 72F, sigma 2 (1-day)"),
        (73, 72, 5.0, "above", "Forecast 73F, threshold 72F, sigma 5 (5-day)"),
        (68, 72, 2.0, "above", "Forecast 68F, threshold 72F, sigma 2 (1-day)"),
        (72, 72, 3.0, "above", "Forecast = threshold, sigma 3"),
    ]
    for forecast, threshold, sigma, direction, label in tests:
        if direction == "above":
            prob = 1.0 - normal_cdf(threshold, mean=forecast, sigma=sigma)
        else:
            prob = normal_cdf(threshold, mean=forecast, sigma=sigma)
        print(f"  {label}")
        print(f"    P({direction} {threshold}) = {prob:.4f} ({prob:.1%})")

    # Test 2: Log-odds roundtrip
    print("\n--- Log-Odds Roundtrip ---")
    for p in [0.10, 0.25, 0.50, 0.75, 0.90]:
        lo = log_odds(p)
        back = from_log_odds(lo)
        print(f"  p={p:.2f} -> log_odds={lo:+.3f} -> back={back:.4f} {'OK' if abs(back - p) < 0.001 else 'FAIL'}")

    # Test 3: Kelly Criterion
    print("\n--- Kelly Criterion ---")
    kelly_tests = [
        (0.60, 0.40, "60% prob, 40c price (strong edge)"),
        (0.55, 0.50, "55% prob, 50c price (small edge)"),
        (0.40, 0.40, "40% prob, 40c price (no edge)"),
        (0.10, 0.03, "10% prob, 3c longshot"),
    ]
    for p, price, label in kelly_tests:
        f = kelly_fraction(p, price)
        bet = position_size(p, price, 50.0)  # $50 bankroll
        print(f"  {label}")
        print(f"    Kelly f*={f:.4f} | Quarter-Kelly bet=${bet:.2f} on $50 bankroll")

    # Test 4: EV with fees
    print("\n--- EV With Fees ---")
    ev_tests = [
        (0.60, 0.40, 2.00, "60% prob, 40c, $2 bet"),
        (0.06, 0.03, 0.50, "6% prob, 3c longshot, $0.50 bet"),
        (0.04, 0.03, 0.50, "4% prob, 3c longshot, $0.50 bet (marginal)"),
    ]
    for p, price, amount, label in ev_tests:
        ev_fee = ev_with_fees(p, price, amount)
        ev_no_fee = ev_with_fees(p, price, amount, fee_rate=0.0)
        print(f"  {label}")
        print(f"    EV with fee: ${ev_fee:+.3f} | EV without: ${ev_no_fee:+.3f} | Fee cost: ${ev_no_fee - ev_fee:.3f}")

    # Test 5: Bayesian update
    print("\n--- Bayesian Update ---")
    bayes_tests = [
        (0.03, 2.0, "3% market, LR=2.0 (crypto milestone underpriced)"),
        (0.03, 1.5, "3% market, LR=1.5 (mild underpricing)"),
        (0.03, 1.0, "3% market, LR=1.0 (no adjustment)"),
        (0.05, 2.5, "5% market, LR=2.5 (strong evidence)"),
    ]
    for prior, lr, label in bayes_tests:
        posterior = bayesian_update(prior, lr)
        print(f"  {label}")
        print(f"    Prior: {prior:.1%} -> Posterior: {posterior:.1%} (old method: {min(prior * lr, 0.20):.1%})")

    # Test 6: Brier score
    print("\n--- Brier Score ---")
    # Perfect forecaster
    perfect = [(0.9, 1), (0.1, 0), (0.8, 1), (0.2, 0)]
    # Random forecaster
    random_f = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
    # Bad forecaster
    bad = [(0.9, 0), (0.1, 1), (0.8, 0), (0.2, 1)]

    print(f"  Good forecaster: {brier_score(perfect):.4f} (should be near 0)")
    print(f"  Random (50/50):  {brier_score(random_f):.4f} (should be 0.25)")
    print(f"  Bad forecaster:  {brier_score(bad):.4f} (should be near 0.5+)")

    print("\n" + "=" * 60)
    print("All tests complete.")
