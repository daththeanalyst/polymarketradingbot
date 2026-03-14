# POLYBOT — Multi-Strategy Polymarket Paper Trading Arena

A quantitative paper trading bot for [Polymarket](https://polymarket.com) that runs **9 strategies in parallel**, each starting with a virtual $100 bankroll. Features a dark neon Streamlit dashboard with real-time leaderboard, equity curves, and trade logs.

Built for strategy research and edge discovery — not financial advice.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What It Does

The bot connects to Polymarket's CLOB (Central Limit Order Book) API and runs 9 independent trading strategies on 5-minute BTC Up/Down binary markets. Each strategy gets $100 in virtual money, makes real decisions based on live market data, and logs every trade for analysis.

**Realistic simulation features:**
- Real order book data from Polymarket CLOB API (bid/ask/depth)
- Walk-the-book fill simulation (no fake midpoint fills)
- 2% fee on winnings (matches Polymarket's actual fee)
- 5-share minimum order enforcement
- BTC price-based resolution (no API polling lag)

---

## Strategies

### Crypto Scalpers (5-min BTC markets)

| # | Strategy | Description |
|---|----------|-------------|
| 1 | **Current** | Classic edge-based entry. 3% min edge, $5 flat bet, profit target + stop loss exits |
| 2 | **Kelly** | Kelly criterion bet sizing. Same signals as Current but sizes bets mathematically |
| 3 | **Aggressive** | Last-60-second entries only. 1% edge threshold, rides positions to resolution |
| 4 | **MicroArb** | Structural arbitrage scanner. Buys both sides when YES+NO < $0.97, plus value-buy fallback |
| 5 | **Momentum** | Pure BTC momentum. Enters when price moves >0.03% in 30 seconds |
| 6 | **MeanRevert** | Contrarian strategy. Bets against the dominant side when odds exceed 70c |

### General Strategies (adapted for crypto markets)

| # | Strategy | Description |
|---|----------|-------------|
| 7 | **HighProb** | Buys the dominant side above 60c. High win rate, small profit per trade |
| 8 | **Longshot** | Buys the underdog below 40c. Low win rate, large payoffs on wins |
| 9 | **Random** | Coin flip baseline (control group). Every strategy should beat this |

---

## Dashboard

Full-featured Streamlit dashboard with 5 tabs:

- **Strategy Arena** — Live leaderboard with rank badges, win rates, streaks, equity curves, and position cards
- **Scalper** — Start/stop the scalper with real-time monitoring
- **Simulator** — Monte Carlo simulation engine for strategy backtesting
- **Trending** — Live market scanner showing active Polymarket markets
- **Config** — Edit bot settings from the browser

**Visual features:** Dark neon theme, glassmorphism cards, animated rank badges (1ST through 9TH), pulsing status indicators, KO badges for busted strategies.

---

## Project Structure

```
polymarket-bot/
├── arena.py              # Strategy Arena engine — 9 strategies, order book sim
├── arena_runner.py       # Background process launcher for the arena
├── dashboard.py          # Streamlit dashboard (5 tabs, dark neon theme)
├── config.py             # All bot settings (bankroll, thresholds, API endpoints)
├── scalper.py            # Original BTC scalper (3 strategy variants)
├── scalper_runner.py     # Background process launcher for the scalper
├── bot.py                # Weather + longshot scanner (Polymarket general markets)
├── strategy.py           # Base strategy classes and signal detection
├── math_utils.py         # Kelly criterion, EV calc, Bayesian updates, Normal CDF
├── markets.py            # Polymarket Gamma API client (market fetching)
├── arbitrage.py          # YES+NO sum arbitrage scanner
├── high_prob.py          # High-probability market scanner (90c+)
├── longshot.py           # Favorite-longshot bias exploit scanner
├── short_term.py         # Short-term crypto market scanner
├── weather.py            # Weather forecast integration (NWS + Open-Meteo)
├── simulator.py          # Monte Carlo profit simulation
├── tracker.py            # Trade logging and CSV management
├── trader.py             # Polymarket CLOB order execution
├── requirements.txt      # Python dependencies
├── launch_dashboard.bat  # One-click dashboard launcher (Windows)
└── .env                  # API keys (not committed)
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up your `.env` file

```bash
cp .env.example .env
# Edit .env with your Polymarket wallet credentials
```

### 3. Launch the dashboard

```bash
streamlit run dashboard.py
```

### 4. Run the Strategy Arena

From the dashboard, click **Start Arena** — or from the command line:

```bash
# Run for 12 hours (default)
python arena_runner.py --duration 720

# Quick 30-minute test
python arena_runner.py --duration 30
```

---

## How It Works

### Order Book Simulation

The bot fetches **real order book depth** from Polymarket's CLOB API for every trade:

```
GET /book?token_id=<token>  →  Full bid/ask ladder with sizes
```

When entering a position, it **walks the order book** level-by-level to calculate the actual fill price you'd get with a real order — accounting for spread, depth, and 5-share minimum.

When exiting, it uses the **bid price** (what you'd actually receive), not the midpoint.

### Resolution Detection

5-minute BTC markets resolve based on whether BTC went up or down during the window. The bot tracks the BTC price at window start and compares at window end — no API polling delays.

### Trade Logging

Every trade logs 17 fields to CSV including entry/exit prices, edge, P&L, hold duration, and resolution outcome. This data feeds future ML model training.

---

## Configuration

All settings are in [`config.py`](config.py):

| Setting | Default | Description |
|---------|---------|-------------|
| `DRY_RUN` | `True` | Paper trading mode (no real money) |
| `SCALP_BET_SIZE` | `$5.00` | Default bet size per trade |
| `SCALP_MIN_EDGE` | `3%` | Minimum edge to enter a trade |
| `SCALP_PROFIT_TARGET` | `50%` | Take profit threshold |
| `SCALP_STOP_LOSS` | `30%` | Cut loss threshold |
| `POLYMARKET_FEE_RATE` | `2%` | Fee on winnings (Polymarket's actual rate) |
| `KELLY_FRACTION` | `0.25` | Quarter Kelly for conservative sizing |

---

## APIs Used

| API | Purpose |
|-----|---------|
| [Polymarket CLOB](https://docs.polymarket.com) | Order book, prices, market data |
| [Polymarket Gamma](https://gamma-api.polymarket.com) | Market discovery, metadata |
| [Binance](https://api.binance.com) | Real-time BTC/ETH spot prices |
| [Open-Meteo](https://open-meteo.com) | Weather forecast data |
| [NWS](https://api.weather.gov) | US weather forecasts |

---

## Tech Stack

- **Python 3.10+** — Core bot logic
- **Streamlit** — Real-time dashboard
- **Plotly** — Interactive charts and equity curves
- **Pandas** — Trade data analysis
- **Polymarket CLOB Client** — Order execution SDK
- **Requests** — API calls with parallel fetching

---

## Disclaimer

This is a **paper trading research tool**. It does not place real trades by default (`DRY_RUN = True`). Use at your own risk. This is not financial advice. Prediction markets carry significant risk of loss.

---

## License

MIT
