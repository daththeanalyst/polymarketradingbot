"""
Polymarket Hybrid Bot
======================
Main entry point. Runs all strategies:
1. Weather Grinder - bets on weather markets where forecast disagrees with price
2. Long Shot Scanner - finds underpriced plausible events with massive multipliers
3. Short-Term Crypto - short-term crypto market edges via technical signals
4. High-Prob Farming - buy near-certain outcomes at 90-99c for micro-profits
5. Structural Arbitrage - find pricing inconsistencies for guaranteed profit

Usage:
  python bot.py              # Full dry run (default)
  python bot.py --longshots  # Only show long shots for manual review
  python bot.py --weather    # Only run weather strategy
  python bot.py --short-term # Only run short-term crypto strategy
  python bot.py --high-prob  # Only run high-probability farming
  python bot.py --arbitrage  # Only run structural arbitrage scanner
  python bot.py --scalp      # Live scalp 5-minute BTC markets
  python bot.py --simulate   # Run Monte Carlo simulation
  python bot.py --stats      # Show paper trading stats
"""

import sys
import time
from datetime import datetime

from config import (
    DRY_RUN, SCAN_INTERVAL_MINUTES, LONGSHOT_AUTO_BET,
    SHORT_TERM_ENABLED, SHORT_TERM_BET_SIZE,
    HIGH_PROB_ENABLED,
    ARBITRAGE_ENABLED, ARBITRAGE_BET_SIZE,
    SCALP_ENABLED,
)
from weather import get_all_forecasts
from markets import get_weather_markets, fetch_all_markets, get_market_prices
from longshot import scan_longshots, display_longshots
from strategy import (
    get_bankroll_split, analyze_weather_market,
    weather_position_size, portfolio_longshots,
)
from trader import Trader
from tracker import log_bet
from high_prob import scan_high_prob, display_high_prob, build_high_prob_portfolio
from arbitrage import scan_arbitrage, display_arbitrage


def print_banner():
    """Print the bot header."""
    print()
    print("=" * 60)
    print("  POLYMARKET HYBRID BOT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'DRY RUN (no real trades)' if DRY_RUN else 'LIVE TRADING'}")
    print("=" * 60)


def run_weather_strategy(trader, bankroll):
    """
    Run the weather grinding strategy.
    Returns list of bets placed (or proposed in dry run).
    """
    print("\n--- WEATHER STRATEGY ---")
    print(f"  Budget: ${bankroll:.2f}")

    # 1. Get weather markets from Polymarket
    weather_markets = get_weather_markets()
    if not weather_markets:
        print("  No weather markets found.")
        return []

    # 2. Get forecasts for all cities
    print("\n  Fetching weather forecasts...")
    forecasts = get_all_forecasts()

    # 3. Match forecasts to markets and find edges
    opportunities = []

    for market in weather_markets:
        city = market.get("city")
        if not city:
            continue

        # Find matching forecast
        city_forecast = forecasts.get(city)
        if not city_forecast:
            # Try partial match
            for fc_city, fc_data in forecasts.items():
                if fc_city.lower() in city.lower() or city.lower() in fc_city.lower():
                    city_forecast = fc_data
                    break

        if not city_forecast:
            continue

        # Match by date
        market_date = market.get("date")
        matched_day = None

        for day in city_forecast:
            if market_date and day.get("date") == market_date:
                matched_day = day
                break

        if not matched_day and city_forecast:
            matched_day = city_forecast[0]  # Use first available day

        if not matched_day:
            continue

        # Analyze
        analysis = analyze_weather_market(market, matched_day)
        if analysis and analysis["should_bet"]:
            opportunities.append(analysis)

    # 4. Sort by edge strength
    opportunities.sort(key=lambda x: abs(x["edge"]), reverse=True)

    # 5. Display and execute
    print(f"\n  Found {len(opportunities)} weather opportunities with edge > threshold")

    bets_placed = []
    remaining = bankroll

    for opp in opportunities:
        if remaining < 0.50:
            break

        # Kelly-sized bet (proportional to edge, not flat)
        side = opp["side"]
        bet_size = weather_position_size(
            opp["forecast_prob"], opp["yes_price"], remaining, side=side
        )
        if bet_size <= 0:
            continue

        # Choose the right token
        token_ids = opp.get("token_ids", [])
        if not token_ids or len(token_ids) < 2:
            continue

        token_id = token_ids[0] if side == "YES" else token_ids[1]
        price = opp["yes_price"] if side == "YES" else opp["no_price"]

        print(f"\n  {opp['title'][:70]}")
        print(f"    Forecast: {opp['forecast_value']} {opp['unit']} vs Threshold: {opp['threshold']} {opp['unit']}")
        print(f"    Market: YES={opp['yes_price']:.2f} | Forecast prob: {opp['forecast_prob']:.1%} | Edge: {opp['edge']:+.1%}")
        print(f"    -> BUY {side} @ ${price:.2f} for ${bet_size:.2f} (Kelly-sized)")

        result = trader.place_bet(token_id, side, bet_size, price)
        bet_data = {**opp, "bet_size": bet_size, "bet_amount": bet_size, "result": result}
        bets_placed.append(bet_data)
        log_bet(bet_data, strategy="weather")
        remaining -= bet_size

    return bets_placed


def run_longshot_strategy(trader, bankroll, auto_bet=None):
    """
    Run the long shot scanning strategy.
    If auto_bet=False, just displays opportunities for manual review.
    """
    if auto_bet is None:
        auto_bet = LONGSHOT_AUTO_BET

    print("\n--- LONG SHOT STRATEGY ---")
    print(f"  Budget: ${bankroll:.2f}")

    # 1. Fetch all markets
    all_markets = fetch_all_markets(max_pages=10)

    # 2. Scan for long shots
    ranked = scan_longshots(all_markets)

    if not ranked:
        print("  No long shots found matching criteria.")
        return []

    # 3. Build portfolio
    portfolio = portfolio_longshots(ranked, bankroll)

    # 4. Display
    display_longshots(portfolio)

    total_cost = sum(p["bet_amount"] for p in portfolio)
    total_potential = sum(p["payout_if_yes"] for p in portfolio)
    print(f"\n  Portfolio: {len(portfolio)} bets | Cost: ${total_cost:.2f} | Max Payout: ${total_potential:.2f}")

    # 5. Execute (or just display)
    bets_placed = []

    if not auto_bet:
        print(f"\n  AUTO-BET is OFF. Review the above and set LONGSHOT_AUTO_BET=True in config.py to enable.")
        print(f"  Or manually place bets on polymarket.com using the market titles above.")
        return portfolio  # Return for display but don't trade

    print(f"\n  AUTO-BET is ON. Placing {len(portfolio)} long shot bets...")
    remaining = bankroll

    for ls in portfolio:
        bet_amount = ls.get("bet_amount", 0.50)
        if remaining < bet_amount:
            break

        token_ids = ls.get("token_ids", [])
        if not token_ids:
            continue

        token_id = token_ids[0]  # YES token
        price = ls["yes_price"]

        print(f"\n  [{ls['yes_price']*100:.1f}c] x{ls['multiplier']} {ls['title'][:60]}")
        print(f"    -> BUY YES @ ${price:.3f} for ${bet_amount:.2f} ({ls['shares']:.0f} shares)")

        result = trader.place_bet(token_id, "BUY", bet_amount, price)
        bets_placed.append({**ls, "result": result})
        log_bet(ls, strategy="longshot")
        remaining -= bet_amount

    return bets_placed


def run_short_term_strategy(trader, bankroll):
    """
    Run the short-term crypto market strategy.
    Returns list of bets placed (or proposed in dry run).
    """
    from short_term import scan_short_term, display_short_term

    print("\n--- SHORT-TERM CRYPTO STRATEGY ---")
    print(f"  Budget: ${bankroll:.2f}")

    if bankroll <= 0:
        print("  No budget allocated. Set SHORT_TERM_SPLIT > 0 in config.py to enable.")
        return []

    opportunities = scan_short_term()
    if not opportunities:
        print("  No short-term crypto opportunities found.")
        return []

    display_short_term(opportunities)

    bets_placed = []
    remaining = bankroll

    for opp in opportunities:
        bet_amount = SHORT_TERM_BET_SIZE
        if remaining < bet_amount:
            break

        token_ids = opp.get("token_ids", [])
        if not token_ids or len(token_ids) < 2:
            continue

        side = opp["side"]
        token_id = token_ids[0] if side == "YES" else token_ids[1]
        price = opp["buy_price"]

        print(f"\n  {opp['coin'].upper()} {opp['timeframe']} | Edge: {opp['edge']:+.1%}")
        print(f"    -> BUY {side} @ ${price:.3f} for ${bet_amount:.2f}")

        result = trader.place_bet(token_id, side, bet_amount, price)
        bet_data = {**opp, "bet_amount": bet_amount, "result": result}
        bets_placed.append(bet_data)
        log_bet(bet_data, strategy="short_term")
        remaining -= bet_amount

    return bets_placed


def run_high_prob_strategy(trader, bankroll):
    """
    Run the high-probability farming strategy.
    Buys near-certain outcomes (90-99c) for small but consistent profits.
    """
    print("\n--- HIGH-PROBABILITY FARMING ---")
    print(f"  Budget: ${bankroll:.2f}")

    if not HIGH_PROB_ENABLED:
        print("  Disabled in config. Set HIGH_PROB_ENABLED=True to enable.")
        return []

    # 1. Scan for high-prob markets
    opportunities = scan_high_prob()

    if not opportunities:
        print("  No high-prob opportunities found right now.")
        return []

    # 2. Build portfolio within budget
    portfolio = build_high_prob_portfolio(opportunities, bankroll)
    display_high_prob(portfolio)

    # 3. Execute (or dry run)
    bets_placed = []
    remaining = bankroll

    for opp in portfolio:
        bet_amount = opp["bet_amount"]
        if remaining < bet_amount:
            break

        token_ids = opp.get("token_ids", [])
        if not token_ids:
            continue

        token_id = token_ids[0]  # YES token
        price = opp["yes_price"]

        print(f"\n  [{price*100:.1f}c] +{opp['net_return_pct']:.1f}% | {opp['title'][:60]}")
        print(f"    -> BUY YES @ ${price:.3f} for ${bet_amount:.2f}")

        result = trader.place_limit_order(token_id, "BUY", bet_amount, price)
        bet_data = {**opp, "bet_amount": bet_amount, "result": result}
        bets_placed.append(bet_data)
        log_bet(bet_data, strategy="high_prob")
        remaining -= bet_amount

    return bets_placed


def run_arbitrage_strategy(trader):
    """
    Run the structural arbitrage scanner.
    Finds sum-to-one and logical pricing inconsistencies.
    """
    print("\n--- STRUCTURAL ARBITRAGE ---")

    if not ARBITRAGE_ENABLED:
        print("  Disabled in config. Set ARBITRAGE_ENABLED=True to enable.")
        return {}

    # 1. Full arbitrage scan
    results = scan_arbitrage()
    display_arbitrage(results)

    # 2. Execute sum-to-one arbitrage (the guaranteed ones)
    bets_placed = []
    sum_opps = results.get("sum_to_one", [])

    for opp in sum_opps[:5]:  # Max 5 arbitrage trades
        token_ids = opp.get("token_ids", [])
        if not token_ids or len(token_ids) < 2:
            continue

        amount = ARBITRAGE_BET_SIZE
        yes_token = token_ids[0]
        no_token = token_ids[1]

        print(f"\n  Arb: {opp['title'][:60]}")
        print(f"    YES=${opp['yes_price']:.3f} + NO=${opp['no_price']:.3f} = ${opp['total_cost']:.3f}")
        print(f"    -> BUY BOTH for ${amount:.2f} | Net profit: ${opp['net_profit']:.4f}")

        result = trader.place_arbitrage(yes_token, no_token, amount)
        bet_data = {**opp, "bet_amount": amount, "result": result}
        bets_placed.append(bet_data)
        log_bet(bet_data, strategy="arbitrage")

    return {"results": results, "bets": bets_placed}


def print_dashboard(split, weather_bets, longshot_bets, short_term_bets=None,
                    high_prob_bets=None, arbitrage_data=None):
    """Print a summary dashboard."""
    if short_term_bets is None:
        short_term_bets = []
    if high_prob_bets is None:
        high_prob_bets = []
    if arbitrage_data is None:
        arbitrage_data = {}

    print("\n" + "=" * 60)
    print("  DASHBOARD SUMMARY")
    print("=" * 60)

    print(f"\n  Bankroll: ${split['total']:.2f}")
    print(f"    Weather fund: ${split['weather']:.2f}")
    print(f"    Long shot fund: ${split['longshot']:.2f}")
    if split.get("short_term", 0) > 0:
        print(f"    Short-term fund: ${split['short_term']:.2f}")

    # Weather summary
    weather_cost = sum(b.get("bet_size", 0) for b in weather_bets)
    print(f"\n  WEATHER BETS: {len(weather_bets)} placed | ${weather_cost:.2f} deployed")
    for b in weather_bets[:5]:
        print(f"    {b.get('side', '?')} @ {b.get('edge', 0):+.0%} edge - {b.get('title', '?')[:50]}")

    # Long shot summary
    if longshot_bets:
        ls_cost = sum(b.get("bet_amount", 0.50) for b in longshot_bets)
        ls_potential = sum(b.get("payout_if_yes", 0) for b in longshot_bets)
        print(f"\n  LONG SHOT BETS: {len(longshot_bets)} | ${ls_cost:.2f} risked | ${ls_potential:.2f} max payout")
        for b in longshot_bets[:5]:
            cat = b.get("category", "?")
            tier = b.get("conviction_tier", "?")
            print(f"    [{b.get('yes_price', 0)*100:.1f}c] x{b.get('multiplier', 0)} [{cat}/{tier}] - {b.get('title', '?')[:45]}")
        if len(longshot_bets) > 5:
            print(f"    ... and {len(longshot_bets) - 5} more")

    # Short-term summary
    if short_term_bets:
        st_cost = sum(b.get("bet_amount", 0) for b in short_term_bets)
        print(f"\n  SHORT-TERM CRYPTO: {len(short_term_bets)} bets | ${st_cost:.2f} deployed")
        for b in short_term_bets[:3]:
            print(f"    {b.get('coin', '?').upper()} {b.get('side', '?')} @ edge {b.get('edge', 0):+.1%} - {b.get('title', '?')[:45]}")

    # High-prob farming summary
    if high_prob_bets:
        hp_cost = sum(b.get("bet_amount", 0) for b in high_prob_bets)
        hp_ev = sum(b.get("ev", 0) for b in high_prob_bets)
        print(f"\n  HIGH-PROB FARMING: {len(high_prob_bets)} bets | ${hp_cost:.2f} deployed | EV: ${hp_ev:+.4f}")
        for b in high_prob_bets[:5]:
            print(f"    [{b['yes_price']*100:.1f}c] +{b['net_return_pct']:.1f}% - {b.get('title', '?')[:50]}")

    # Arbitrage summary
    arb_results = arbitrage_data.get("results", {})
    arb_bets = arbitrage_data.get("bets", [])
    arb_total = arb_results.get("total", 0)
    if arb_total > 0 or arb_bets:
        print(f"\n  ARBITRAGE: {arb_total} opportunities found | {len(arb_bets)} trades placed")
        for b in arb_bets[:3]:
            print(f"    Gap: {b.get('gap', 0)*100:.1f}c | Profit: ${b.get('net_profit', 0):.4f} - {b.get('title', '?')[:45]}")

    print(f"\n  Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")
    print("=" * 60)


def run_simulation():
    """Run Monte Carlo simulation on current longshot portfolio."""
    from simulator import simulate_portfolio, display_simulation, display_histogram, calc_at_least_one_hit

    print("\n--- MONTE CARLO SIMULATION ---")
    print("  Building current long shot portfolio...")

    all_markets = fetch_all_markets(max_pages=10)
    ranked = scan_longshots(all_markets)

    split = get_bankroll_split()
    portfolio = portfolio_longshots(ranked, split["longshot"])

    if not portfolio:
        print("  No bets in portfolio to simulate.")
        return

    display_longshots(portfolio)

    # Show hit probability
    probs = [b["estimated_prob"] for b in portfolio]
    p_hit = calc_at_least_one_hit(probs)
    total_cost = sum(b["bet_amount"] for b in portfolio)
    print(f"\n  Portfolio: {len(portfolio)} bets | Cost: ${total_cost:.2f}")
    print(f"  P(at least 1 hit): {p_hit:.1%}")

    print(f"\n  Running 10,000 simulations...")
    sim = simulate_portfolio(portfolio, num_simulations=10000)
    display_simulation(sim)
    display_histogram(sim["results_raw"])


def main():
    """Main bot entry point."""
    print_banner()

    # Handle simulation/stats commands
    if "--simulate" in sys.argv:
        run_simulation()
        return
    if "--stats" in sys.argv:
        from tracker import display_stats
        display_stats()
        return
    if "--scalp" in sys.argv:
        from scalper import LiveScalper
        trader = Trader()
        trader.connect()
        scalper = LiveScalper(trader)
        scalper.run(duration_minutes=30)
        return

    # Parse command line args
    only_longshots = "--longshots" in sys.argv
    only_weather = "--weather" in sys.argv
    only_short_term = "--short-term" in sys.argv
    only_high_prob = "--high-prob" in sys.argv
    only_arbitrage = "--arbitrage" in sys.argv

    # Initialize
    split = get_bankroll_split()
    trader = Trader()
    trader.connect()

    weather_bets = []
    longshot_bets = []
    short_term_bets = []
    high_prob_bets = []
    arbitrage_data = {}

    # Run strategies
    if only_high_prob:
        high_prob_bets = run_high_prob_strategy(trader, split["total"])
    elif only_arbitrage:
        arbitrage_data = run_arbitrage_strategy(trader)
    elif only_short_term:
        short_term_bets = run_short_term_strategy(trader, split["short_term"])
    elif only_longshots:
        longshot_bets = run_longshot_strategy(trader, split["longshot"])
    elif only_weather:
        weather_bets = run_weather_strategy(trader, split["weather"])
    else:
        # Run all enabled strategies
        weather_bets = run_weather_strategy(trader, split["weather"])
        longshot_bets = run_longshot_strategy(trader, split["longshot"])
        if SHORT_TERM_ENABLED and split["short_term"] > 0:
            short_term_bets = run_short_term_strategy(trader, split["short_term"])
        if HIGH_PROB_ENABLED:
            high_prob_bets = run_high_prob_strategy(trader, split["total"] * 0.10)
        if ARBITRAGE_ENABLED:
            arbitrage_data = run_arbitrage_strategy(trader)

    # Dashboard
    print_dashboard(split, weather_bets, longshot_bets, short_term_bets,
                    high_prob_bets, arbitrage_data)

    print(f"\nDone. Next scan in {SCAN_INTERVAL_MINUTES} minutes.")
    print("Press Ctrl+C to stop.\n")


def run_loop():
    """Run the bot in a loop."""
    while True:
        try:
            main()
            print(f"Sleeping {SCAN_INTERVAL_MINUTES} minutes...")
            time.sleep(SCAN_INTERVAL_MINUTES * 60)
        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"\n[ERROR] Bot crashed: {e}")
            print("Retrying in 5 minutes...")
            time.sleep(300)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        run_loop()
    else:
        main()
