"""
Polymarket Hybrid Bot Configuration
====================================
Edit these settings to control how the bot behaves.
"""

# ---------------------
# BANKROLL SETTINGS
# ---------------------
TOTAL_BANKROLL = 50.00           # Your total starting money in USDC
WEATHER_SPLIT = 0.70             # 70% goes to weather grinding
LONGSHOT_SPLIT = 0.30            # 30% goes to long shot bets

# ---------------------
# WEATHER STRATEGY
# ---------------------
WEATHER_BET_SIZE = 2.50          # Max weather bet (Kelly calculates actual size)
WEATHER_MIN_EDGE = 0.05          # Only bet if edge > 5% (Normal CDF is more precise)
WEATHER_MAX_POSITIONS = 20       # Max simultaneous weather bets

# ---------------------
# LONG SHOT STRATEGY
# ---------------------
LONGSHOT_BET_SIZE = 0.50         # Bet $0.50 per long shot
LONGSHOT_MAX_PRICE = 0.05        # Only buy tokens priced at 5¢ or less (20x+ multiplier)
LONGSHOT_MAX_POSITIONS = 30      # Max simultaneous long shots
LONGSHOT_MIN_VOLUME = 1000       # Minimum market volume (skip dead markets)
LONGSHOT_TOP_PICKS = 10          # Show top 10 long shots for review

# Keywords to EXCLUDE from long shots (fantasy/impossible events)
LONGSHOT_EXCLUDE_KEYWORDS = [
    "alien", "ufo", "extraterrestrial",
    "god", "supernatural", "miracle",
    "sun explode", "earth destroy", "asteroid hit",
    "zombie", "vampire", "ghost",
    "time travel", "teleport",
]

# Categories to PREFER for long shots (plausible surprises)
LONGSHOT_PREFER_CATEGORIES = [
    "politics", "elections", "economy",
    "crypto", "bitcoin", "ethereum",
    "weather", "hurricane", "earthquake",
    "sports", "championship",
    "technology", "ai",
]

# ---------------------
# CATEGORY SCORING (smart filtering based on favorite-longshot bias research)
# ---------------------
# Positive = systematically underpriced (good bets)
# Negative = systematically overpriced (bad bets, avoid)
CATEGORY_SCORES = {
    "crypto_milestone": 20,
    "ceasefire": 15,
    "regulatory_clarity": 15,
    "tech_milestone": 10,
    "economic_event": 10,
    "weather_event": 5,
    "sports_championship": 0,
    "general": 0,
    "individual_politician": -15,
    "sports_team_winner": -10,
    "dramatic_upheaval": -20,
}

# Keywords that map markets to categories automatically
CATEGORY_KEYWORDS = {
    "crypto_milestone": [
        "bitcoin", "btc ", "ethereum", " eth ", "crypto",
        "$100k", "$150k", "$200k", "$250k", "$500k", "$1m",
        "etf approv", "halving", "solana", "dogecoin",
    ],
    "ceasefire": [
        "ceasefire", "peace deal", "peace agreement", "truce",
        "de-escalat", "treaty", "peace negotiat",
    ],
    "regulatory_clarity": [
        "sec approv", "regulation pass", "regulatory",
        "legislation", "bill pass", "executive order",
    ],
    "tech_milestone": [
        "product launch", "release date", "artificial general intelligence",
        "achieve agi", "self-driving", "fusion energy", " ipo ",
        "openai", "google deepmind", "spacex",
    ],
    "economic_event": [
        "fed cut", "rate cut", "interest rate", "recession",
        "gdp", "inflation below", "unemployment",
    ],
    "individual_politician": [
        "win the 2026", "win the 2027", "win the 2028",
        "wins election", "wins presidency", "wins primary",
        "elected president", "nominee", "wins nomination",
        "bolsonaro", "le pen", "modi wins", "desantis",
        "haley wins", "rfk wins",
    ],
    "sports_team_winner": [
        "win the 2026 nhl", "win the 2026 nba", "win the 2026 nfl",
        "win the 2026 mlb", "win the 2027 nhl", "win the 2027 nba",
        "wins stanley cup", "wins super bowl", "wins world series",
        "win the nba finals", "win the nba eastern",
        "win the nba western", "win the nhl",
    ],
    "dramatic_upheaval": [
        "coup", "impeach", "assassin", "martial law",
        "civil war", "regime change", "overthrow",
        "declare war", "nuclear strike", "invaded",
    ],
}

# Max bets per category (diversification)
LONGSHOT_MAX_PER_CATEGORY = 2

# Conviction-based bet sizing (replaces flat LONGSHOT_BET_SIZE for portfolio)
CONVICTION_TIERS = {
    "high": 1.50,      # Score >= 50: strong catalyst, underpriced category
    "medium": 0.75,    # Score 30-49: decent bet
    "low": 0.25,       # Score < 30: exploration bet
}

# ---------------------
# CITIES FOR WEATHER
# ---------------------
# Format: (name, latitude, longitude, country)
CITIES = [
    ("New York", 40.7128, -74.0060, "US"),
    ("Chicago", 41.8781, -87.6298, "US"),
    ("Los Angeles", 34.0522, -118.2437, "US"),
    ("London", 51.5074, -0.1278, "UK"),
    ("Paris", 48.8566, 2.3522, "FR"),
    ("Seoul", 37.5665, 126.9780, "KR"),
    ("Buenos Aires", -34.6037, -58.3816, "AR"),
    ("Tokyo", 35.6762, 139.6503, "JP"),
    ("Sydney", -33.8688, 151.2093, "AU"),
    ("Berlin", 52.5200, 13.4050, "DE"),
]

# ---------------------
# BOT SETTINGS
# ---------------------
DRY_RUN = True                   # True = just show what it WOULD do (no real trades)
SCAN_INTERVAL_MINUTES = 60       # How often to scan for new opportunities
LONGSHOT_AUTO_BET = False        # False = show list for you to pick. True = auto bet.

# ---------------------
# SHORT-TERM CRYPTO STRATEGY
# ---------------------
SHORT_TERM_ENABLED = True
SHORT_TERM_SPLIT = 0.00          # Start at 0% until validated (70/30 stays intact)
SHORT_TERM_BET_SIZE = 0.50       # Small bets on short-term crypto
SHORT_TERM_MIN_EDGE = 0.06       # 6% min edge (higher due to dynamic fees)
SHORT_TERM_MAX_POSITIONS = 5     # Max simultaneous short-term bets
SHORT_TERM_COINS = ["bitcoin", "ethereum"]

# ---------------------
# HIGH-PROBABILITY FARMING (elite quant strategy)
# ---------------------
# Buy YES on markets at 90-98c where outcome is nearly certain.
# Small profit per trade, but compounds rapidly over many trades.
HIGH_PROB_ENABLED = True
HIGH_PROB_MIN_PRICE = 0.90       # Only buy YES at 90c+ (near-certainties)
HIGH_PROB_MIN_VOLUME = 10000     # Skip illiquid markets
HIGH_PROB_BET_SIZE = 0.50        # Small bets, many markets
HIGH_PROB_MAX_POSITIONS = 10     # Max simultaneous high-prob bets

# ---------------------
# STRUCTURAL ARBITRAGE (elite quant strategy)
# ---------------------
# Find pricing inconsistencies: YES + NO < $1, or logically inconsistent markets.
# Guaranteed or near-guaranteed profit from structural mispricing.
ARBITRAGE_ENABLED = True
ARBITRAGE_MIN_GAP = 0.025        # 2.5% minimum gap (covers 2% fee + buffer)
ARBITRAGE_BET_SIZE = 1.00        # Larger bets for guaranteed profits
ARBITRAGE_MAX_POSITIONS = 5      # Max simultaneous arbitrage positions

# ---------------------
# LIVE SCALPING (5-minute BTC Up/Down markets)
# ---------------------
# Exploits the 30-90 second lag between BTC spot price and Polymarket odds.
SCALP_ENABLED = True
SCALP_BET_SIZE = 5.00            # Dollar amount per scalp trade (min order = 5 shares)
SCALP_MAX_POSITIONS = 1          # Only 1 position at a time (focus)
SCALP_POLL_INTERVAL = 2          # Check prices every 2 seconds (faster signal detection)
SCALP_MIN_EDGE = 0.03            # 3% minimum edge to enter (covers ~1.5% fees)
SCALP_PROFIT_TARGET = 0.50       # Take profit at 50% gain
SCALP_STOP_LOSS = 0.30           # Cut losses at 30% loss
SCALP_HEDGE_THRESHOLD = 0.20     # Hedge if losing 20%+ and odds swing
SCALP_MARKET_TYPE = "5min"              # "5min", "15min", or "1hour"

# ---------------------
# SCALP STRATEGY VARIANTS (for paper trading comparison)
# ---------------------
# Strategy 2: "Kelly" -- Kelly criterion bet sizing + stricter entry
SCALP_KELLY_ENABLED = True
SCALP_KELLY_FRACTION = 0.25         # Quarter Kelly for bet sizing
SCALP_KELLY_MIN_EDGE = 0.03         # Same edge threshold, Kelly filters naturally
SCALP_KELLY_MAX_BET = 10.00         # Max bet even if Kelly says more
SCALP_KELLY_MIN_BET = 5.00          # Minimum bet (Polymarket minimum)

# Strategy 3: "Aggressive" -- last-second, low-threshold, ride-to-resolution
SCALP_AGGRESSIVE_ENABLED = True
SCALP_AGGRESSIVE_MIN_EDGE = 0.01    # 1% edge threshold (very low)
SCALP_AGGRESSIVE_BET_SIZE = 5.00    # Flat bet size
SCALP_AGGRESSIVE_MAX_TIME = 60      # ONLY enter with < 60 seconds left
SCALP_AGGRESSIVE_MOMENTUM_ONLY = True  # Enter on momentum alone if edge > 1%

# Paper trading realism: simulated slippage + fees on fills
SCALP_PAPER_SLIPPAGE = 0.02         # 2% slippage on paper fills (simulates spread + delay)
SCALP_PAPER_FEE = 0.02              # 2% fee on winnings (Polymarket takes this)

# ---------------------
# MATHEMATICAL SETTINGS
# ---------------------
POLYMARKET_FEE_RATE = 0.02       # 2% fee on winnings
KELLY_FRACTION = 0.25            # Quarter Kelly (safest for beginners with $50)
MAX_BET_PCT = 0.05               # Never bet more than 5% of bankroll per position

# Weather forecast uncertainty (standard deviation in degrees F, by days out)
# Based on NWS forecast verification stats: closer forecasts are more accurate
WEATHER_SIGMA = {
    0: 1.5,   # Today: very accurate
    1: 2.0,   # Tomorrow: good
    2: 3.0,   # 2 days out: decent
    3: 4.0,   # 3 days out: moderate
    4: 4.5,   # 4 days out: uncertain
    5: 5.0,   # 5+ days out: quite uncertain
}

# ---------------------
# API ENDPOINTS (don't change these)
# ---------------------
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
NWS_API = "https://api.weather.gov"
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"
COINGECKO_API = "https://api.coingecko.com/api/v3"
BINANCE_API = "https://api.binance.com/api/v3"
CHAIN_ID = 137  # Polygon mainnet
