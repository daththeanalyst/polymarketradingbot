"""
Hybrid Strategy Engine
=======================
Combines two strategies:
1. Weather Grinder -- consistent small-edge bets using forecast data
2. Long Shot Portfolio -- tiny bets on underpriced plausible events

Mathematical foundations:
- Normal CDF for weather probability (replaces hardcoded lookup)
- Kelly Criterion for position sizing (proven optimal bet sizing)
- Bayesian updating for longshot probability estimation
- EV with fees for accurate profitability assessment
"""

from datetime import date

from config import (
    TOTAL_BANKROLL, WEATHER_SPLIT, LONGSHOT_SPLIT, SHORT_TERM_SPLIT,
    WEATHER_BET_SIZE, WEATHER_MIN_EDGE,
    LONGSHOT_MAX_POSITIONS,
    LONGSHOT_MAX_PER_CATEGORY, CONVICTION_TIERS,
    WEATHER_SIGMA, POLYMARKET_FEE_RATE, KELLY_FRACTION, MAX_BET_PCT,
)
from math_utils import (
    normal_cdf, kelly_fraction, position_size,
    ev_with_fees, bayesian_update,
)


# =====================
# BANKROLL MANAGEMENT
# =====================

def get_bankroll_split(total=None):
    """Split total bankroll between strategies."""
    if total is None:
        total = TOTAL_BANKROLL
    return {
        "total": total,
        "weather": round(total * WEATHER_SPLIT, 2),
        "longshot": round(total * LONGSHOT_SPLIT, 2),
        "short_term": round(total * SHORT_TERM_SPLIT, 2),
    }


# =====================
# WEATHER STRATEGY
# =====================

def forecast_to_probability(forecast_value, threshold, direction, metric="high_temp", days_out=1):
    """
    Convert a weather forecast into a probability using the Normal CDF.

    The actual temperature is modeled as a normal distribution centered
    on the forecast value, with uncertainty (sigma) that increases for
    forecasts further in the future.

    This replaces the old 10-step hardcoded lookup table that had
    discontinuous jumps (4.9F diff = 75%, 5.0F diff = 85%).

    Args:
        forecast_value: The forecasted temperature (e.g., 78F)
        threshold: The market's threshold (e.g., "Will it exceed 72F?")
        direction: "above" or "below"
        metric: "high_temp" or "low_temp"
        days_out: How many days in the future (more days = more uncertainty)

    Math:
        T ~ Normal(forecast_value, sigma^2)
        P(T > threshold) = 1 - Phi((threshold - forecast) / sigma)

    Example:
        forecast=78, threshold=72, sigma=2 (1-day):
        P(above 72) = 1 - Phi((72-78)/2) = 1 - Phi(-3) = 99.87%

        forecast=73, threshold=72, sigma=5 (5-day):
        P(above 72) = 1 - Phi((72-73)/5) = 1 - Phi(-0.2) = 57.9%
    """
    if forecast_value is None or threshold is None:
        return None

    # Get sigma based on forecast horizon
    sigma = WEATHER_SIGMA.get(min(days_out, 5), 5.0)

    if direction == "above":
        # P(actual temp > threshold)
        prob = 1.0 - normal_cdf(threshold, mean=forecast_value, sigma=sigma)
    elif direction == "below":
        # P(actual temp < threshold)
        prob = normal_cdf(threshold, mean=forecast_value, sigma=sigma)
    else:
        return 0.50

    # Never be 100% certain about weather
    return max(0.02, min(0.98, prob))


def calculate_edge(forecast_prob, market_price):
    """
    Calculate the edge: how much the market is mispriced.

    edge = forecast_probability - market_price
    Positive edge = market underprices the outcome (buy YES)
    Negative edge = market overprices the outcome (buy NO)
    """
    if forecast_prob is None or market_price is None:
        return 0

    return forecast_prob - market_price


def should_bet_weather(edge, min_edge=None):
    """Only bet if the edge exceeds the minimum threshold."""
    if min_edge is None:
        min_edge = WEATHER_MIN_EDGE
    return abs(edge) >= min_edge


def pick_side(edge):
    """
    Decide whether to buy YES or NO.
    Positive edge -> buy YES (market underprices it)
    Negative edge -> buy NO (market overprices it)
    """
    if edge > 0:
        return "YES"
    elif edge < 0:
        return "NO"
    return None


def quarter_kelly(prob, price, fee_rate=None):
    """
    Quarter-Kelly position sizing for binary markets.
    Delegates to the proper Kelly implementation in math_utils.
    """
    if fee_rate is None:
        fee_rate = POLYMARKET_FEE_RATE
    f = kelly_fraction(prob, price, fee_rate)
    return max(0, min(f * KELLY_FRACTION, MAX_BET_PCT))


def weather_position_size(forecast_prob, market_price, bankroll, side="YES"):
    """
    Calculate how much to bet on a weather market using Kelly Criterion.

    Instead of flat $1 bets, the size is proportional to your edge:
    bigger edge = bigger bet (automatically via Kelly math).

    Args:
        forecast_prob: Our estimated probability from Normal CDF
        market_price: The YES price on the market
        bankroll: Available weather bankroll
        side: "YES" or "NO"

    Returns:
        Dollar amount to bet (0 if no edge, min $0.50 if betting)
    """
    if side == "NO":
        # For NO bets, our probability of winning = 1 - forecast_prob
        # and the price is the NO price = 1 - yes_price
        p = 1.0 - forecast_prob
        price = 1.0 - market_price
    else:
        p = forecast_prob
        price = market_price

    # Calculate Kelly-optimal bet size
    bet = position_size(
        p, price, bankroll,
        fraction=KELLY_FRACTION,
        fee_rate=POLYMARKET_FEE_RATE,
        max_pct=MAX_BET_PCT,
    )

    # Cap at WEATHER_BET_SIZE
    bet = min(bet, WEATHER_BET_SIZE)

    # Minimum practical bet on Polymarket
    if 0 < bet < 0.50:
        bet = 0.50

    return round(bet, 2)


def analyze_weather_market(market, forecast_day):
    """
    Analyze a single weather market against forecast data.
    Returns analysis dict with recommendation.
    """
    # Get market price
    prices = market.get("outcomePrices", [])
    if not prices or len(prices) < 2:
        return None

    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (ValueError, TypeError):
        return None

    # Get forecast value for the right metric
    threshold = market.get("threshold")
    direction = market.get("direction")
    metric = market.get("metric", "high_temp")

    if metric == "high_temp":
        forecast_value = forecast_day.get("high_f")
        if market.get("unit") == "C":
            forecast_value = forecast_day.get("high_c")
    elif metric == "low_temp":
        forecast_value = forecast_day.get("low_f")
        if market.get("unit") == "C":
            forecast_value = forecast_day.get("low_c")
    else:
        forecast_value = None

    if forecast_value is None or threshold is None:
        return None

    # Calculate days_out from market date
    days_out = 1  # Default to tomorrow
    market_date = market.get("date")
    if market_date:
        try:
            market_date_obj = date.fromisoformat(market_date)
            today = date.today()
            days_out = max(0, (market_date_obj - today).days)
        except (ValueError, TypeError):
            days_out = 1

    # Calculate probability using Normal CDF and edge
    forecast_prob = forecast_to_probability(
        forecast_value, threshold, direction, metric, days_out=days_out
    )
    edge = calculate_edge(forecast_prob, yes_price)
    side = pick_side(edge)
    bet = should_bet_weather(edge)

    return {
        "title": market.get("title", "?"),
        "city": market.get("city"),
        "date": market_date,
        "days_out": days_out,
        "forecast_value": forecast_value,
        "threshold": threshold,
        "unit": market.get("unit", "F"),
        "direction": direction,
        "forecast_prob": round(forecast_prob, 4),
        "yes_price": yes_price,
        "no_price": no_price,
        "edge": round(edge, 4),
        "side": side,
        "should_bet": bet,
        "token_ids": market.get("token_ids", []),
    }


# =====================
# LONG SHOT STRATEGY
# =====================

def get_conviction_tier(score):
    """Map score to conviction tier for position sizing."""
    if score >= 50:
        return "high"
    elif score >= 30:
        return "medium"
    else:
        return "low"


def score_to_likelihood_ratio(score):
    """
    Convert a longshot score into a Bayesian likelihood ratio.

    The score reflects how underpriced we think a category is.
    A higher score means the evidence (category analysis, volume,
    multiplier sweet spot) is more consistent with underpricing.

    These ratios are conservative -- overconfidence is the #1 risk.
    """
    if score >= 50:
        return 2.5
    elif score >= 40:
        return 2.0
    elif score >= 30:
        return 1.7
    elif score >= 20:
        return 1.4
    elif score >= 10:
        return 1.2
    else:
        return 1.0  # No adjustment, trust the market


def evaluate_longshot(longshot, bet_amount=None):
    """
    Evaluate a longshot bet using Bayesian probability and proper EV.

    Old approach: estimated_prob = market_price * arbitrary_multiplier (1.5x-3x)
    New approach: Use market price as Bayesian prior, update with
                  evidence (category score) via likelihood ratio.

    This is better because:
    1. The market price IS information -- other bettors have opinions
    2. We only adjust based on our specific edge (category analysis)
    3. Bayes' theorem correctly handles the base rate
    4. EV calculation includes Polymarket's 2% fee
    """
    price = longshot["yes_price"]
    score = longshot.get("score", 0)

    # Determine bet size from conviction tier
    tier = get_conviction_tier(score)
    if bet_amount is None:
        bet_amount = CONVICTION_TIERS[tier]

    # BAYESIAN PROBABILITY ESTIMATION
    # Prior = market price (what the crowd thinks)
    # Likelihood ratio = from our category/signal analysis
    lr = score_to_likelihood_ratio(score)
    estimated_real_prob = bayesian_update(price, lr)

    # Cap at 25% -- if we think it's more than 25%, it's not a longshot
    estimated_real_prob = min(estimated_real_prob, 0.25)

    # EXPECTED VALUE WITH FEES (accounts for Polymarket's 2% cut)
    ev = ev_with_fees(estimated_real_prob, price, bet_amount, POLYMARKET_FEE_RATE)

    shares = bet_amount / price
    net_payout = shares * (1.0 - POLYMARKET_FEE_RATE)

    return {
        **longshot,
        "estimated_prob": round(estimated_real_prob, 4),
        "likelihood_ratio": lr,
        "bet_amount": bet_amount,
        "conviction_tier": tier,
        "shares": round(shares, 1),
        "payout_if_yes": round(net_payout, 2),
        "expected_value": round(ev, 2),
        "ev_positive": ev > 0,
    }


def portfolio_longshots(ranked_longshots, bankroll):
    """
    Build a diversified portfolio of long shot bets within budget.
    Enforces category limits and uses conviction-based sizing.

    Correlation adjustment: 2nd bet in same category gets 30% reduction
    because correlated bets (e.g., two crypto bets) tend to win/lose together.
    """
    bets = []
    remaining = bankroll
    category_counts = {}

    for ls in ranked_longshots:
        if remaining < CONVICTION_TIERS["low"]:
            break
        if len(bets) >= LONGSHOT_MAX_POSITIONS:
            break

        # Enforce category diversification
        cat = ls.get("category", "general")
        current_count = category_counts.get(cat, 0)
        if current_count >= LONGSHOT_MAX_PER_CATEGORY:
            continue

        # Determine bet size from conviction tier
        tier = get_conviction_tier(ls.get("score", 0))
        bet_size = CONVICTION_TIERS[tier]

        # Correlation adjustment: reduce 2nd bet in same category by 30%
        if current_count > 0:
            bet_size = round(bet_size * 0.7, 2)

        if remaining < bet_size:
            if remaining >= CONVICTION_TIERS["low"]:
                bet_size = CONVICTION_TIERS["low"]
            else:
                break

        evaluated = evaluate_longshot(ls, bet_size)

        if evaluated["ev_positive"]:
            bets.append(evaluated)
            remaining -= bet_size
            category_counts[cat] = current_count + 1

    return bets


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 60)
    print("STRATEGY ENGINE TEST (with math upgrades)")
    print("=" * 60)

    # Test bankroll split
    split = get_bankroll_split()
    print(f"\nBankroll Split:")
    print(f"  Total:    ${split['total']:.2f}")
    print(f"  Weather:  ${split['weather']:.2f} ({WEATHER_SPLIT*100:.0f}%)")
    print(f"  Longshot: ${split['longshot']:.2f} ({LONGSHOT_SPLIT*100:.0f}%)")

    # Test weather probability (Normal CDF vs old lookup)
    print(f"\nWeather Probability (Normal CDF):")
    examples = [
        (78, 72, "above", 1),   # 6F above, 1-day forecast
        (73, 72, "above", 1),   # 1F above, 1-day
        (73, 72, "above", 5),   # 1F above, 5-day (more uncertain)
        (68, 72, "above", 1),   # 4F below, 1-day
        (71, 72, "above", 1),   # 1F below, 1-day
        (60, 65, "below", 2),   # 5F below threshold, 2-day
    ]
    for forecast, threshold, direction, days in examples:
        prob = forecast_to_probability(forecast, threshold, direction, days_out=days)
        edge = calculate_edge(prob, 0.50)
        side = pick_side(edge)
        bet = should_bet_weather(edge)
        bet_size = weather_position_size(prob, 0.50, 35.0, side=side) if bet else 0
        print(f"  Forecast: {forecast}F vs {threshold}F ({direction}, {days}-day)")
        print(f"    Prob: {prob:.1%} | Edge: {edge:+.1%} | Side: {side} | Bet: {bet} | Size: ${bet_size:.2f}")

    # Test long shot evaluation (Bayesian vs old method)
    print(f"\nLong Shot EV (Bayesian):")
    test_longshots = [
        {"title": "BTC hits $200K", "yes_price": 0.02, "multiplier": 50, "score": 35, "volume": 50000, "tags": ["crypto"]},
        {"title": "Cat 5 hurricane by May", "yes_price": 0.03, "multiplier": 33.3, "score": 30, "volume": 10000, "tags": ["weather"]},
        {"title": "Some random event", "yes_price": 0.01, "multiplier": 100, "score": 10, "volume": 500, "tags": []},
    ]
    for ls in test_longshots:
        ev = evaluate_longshot(ls)
        print(f"  {ls['title']}")
        print(f"    Price: {ls['yes_price']*100:.0f}c | Score: {ls['score']} | LR: {ev['likelihood_ratio']}x")
        print(f"    Bayesian prob: {ev['estimated_prob']:.1%} | EV: ${ev['expected_value']:+.2f} {'[BET]' if ev['ev_positive'] else '[SKIP]'}")
        print(f"    ${ev['bet_amount']:.2f} -> {ev['shares']:.0f} shares -> ${ev['payout_if_yes']:.2f} payout (after 2% fee)")
