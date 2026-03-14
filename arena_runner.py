"""
Arena Runner — Subprocess wrapper for dashboard integration.
Launches the ArenaRunner as a background process.

Usage:
  python arena_runner.py --duration 720 --coin btc
"""

import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from arena import ArenaRunner


def main():
    parser = argparse.ArgumentParser(description="Run Strategy Arena")
    parser.add_argument("--duration", type=int, default=720, help="Duration in minutes")
    parser.add_argument("--coin", default="btc", help="Crypto coin: btc, eth")
    args = parser.parse_args()

    runner = ArenaRunner(coin=args.coin)
    runner.run_with_state_file(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
