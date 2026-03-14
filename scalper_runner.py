"""
Scalper Runner — Subprocess wrapper for dashboard integration.
Launches the LiveScalper with JSON state file output.

Usage:
  python scalper_runner.py --duration 30 --state-file scalper_state.json
"""

import argparse
import os
import sys

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from trader import Trader
from scalper import LiveScalper


def main():
    parser = argparse.ArgumentParser(description="Run live scalper with state file output")
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes")
    parser.add_argument("--state-file", default="scalper_state.json", help="Path to state JSON file")
    parser.add_argument("--market-type", default="5min", help="Market type: 5min or 15min")
    parser.add_argument("--coin", default="btc", help="Coin: btc, eth")
    args = parser.parse_args()

    trader = Trader()
    trader.connect()

    scalper = LiveScalper(trader, coin=args.coin)
    scalper.run_with_state_file(
        duration_minutes=args.duration,
        state_file=args.state_file,
    )


if __name__ == "__main__":
    main()
