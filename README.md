# POLYBOT — Multi-Strategy Polymarket Paper Trading Arena

A quantitative paper trading bot for [Polymarket](https://polymarket.com) that runs **10 strategies in parallel**, each starting with a virtual $100 bankroll. Features a dark neon Streamlit dashboard with real-time leaderboard, equity curves, trade logs, and a **real-time whale tracker** that mirrors profitable traders via Polygon WebSocket.

Built for strategy research and edge discovery — not financial advice.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What It Does

The bot connects to Polymarket's CLOB (Central Limit Order Book) API and runs 10 independent trading strategies on 5-minute BTC Up/Down binary markets. Each strategy gets $100 in virtual money, makes real decisions based on live market data, and logs every trade for analysis.

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

### Whale Copy-Trading

| # | Strategy | Description |
|---|----------|-------------|
| 10 | **WhaleMirror** | Real-time whale copy-trading. Monitors 11 profitable wallets via Polygon WebSocket (~2-3s latency) + Data API fallback. Enters when 2+ whales agree on direction. Bet sizing scaled to 10% of whale's USDC amount |

---

## Tracked Whales

The WhaleMirror strategy monitors **11 profitable Polymarket wallets** in real-time using on-chain event detection:

| Whale | Profile | Style | All-Time P&L |
|-------|---------|-------|--------------|
| **MuseumOfBees** | [View Profile](https://polymarket.com/profile/0x61276aba49117fd9299707d5d573652949d5c977) | Crypto scalper | Profitable |
| **tugao9** | [View Profile](https://polymarket.com/profile/0x970e744a34cd0795ff7b4ba844018f17b7fd5c26) | Crypto scalper | Extremely profitable |
| **Realistic-Swivel** | [View Profile](https://polymarket.com/profile/0x2eb5714ff6f20f5f9f7662c556dbef5e1c9bf4d4) | Crypto scalper | Extremely profitable |
| **2B9S** | [View Profile](https://polymarket.com/profile/0x87650b9f63563f7c456d9bbcceee5f9faf06ed81) | Weather + Solana + ETH | Profitable |
| **aekghas** | [View Profile](https://polymarket.com/profile/0xb2a3623364c33561d8312e1edb79eb941c798510) | War / Geopolitical | +$54K |
| **anoin123** | [View Profile](https://polymarket.com/profile/0x96489abcb9f583d6835c8ef95ffc923d05a86825) | Everything (high volume) | -$4.87M |
| **Wickier** | [View Profile](https://polymarket.com/profile/0x1cc16713196d456f86fa9c7387dd326a7f73b8df) | Mixed | +$220K |
| **chungguskhan** | [View Profile](https://polymarket.com/profile/0x7744bfd749a70020d16a1fcbac1d064761c9999e) | Mixed | +$750K |
| **wan123** | [View Profile](https://polymarket.com/profile/0xde7be6d489bce070a959e0cb813128ae659b5f4b) | Mixed | +$360K |
| **no1yet** | [View Profile](https://polymarket.com/profile/0x4d49acb0ae1c463eb5b1947d174141b812ba7450) | Mixed | +$34K |
| **myfirstpubes** | [View Profile](https://polymarket.com/profile/0xad142563a8d80e3f6a18ca5fa5936027942bbf69) | Mixed | +$56K |

**Detection method:** Polygon WebSocket subscribes to `OrderFilled` events on the CTF Exchange contract (`0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`), filtering for these 11 addresses as maker or taker. Trades are detected in ~2-3 seconds (one block confirmation). Data API polling runs every 5 seconds as fallback.

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
├── arena.py              # Strategy Arena engine — 10 strategies, order book sim
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
├── whale_watcher.py      # Real-time whale monitor (Polygon WebSocket + Data API)
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
