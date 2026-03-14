"""
Polymarket Bot Dashboard — Full Control Center
================================================
5-tab Streamlit dashboard to monitor, control, and simulate.

Launch:
  streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import subprocess
import sys
import os
import re
import json
import time
import importlib
import requests
from datetime import datetime

# ---------------------
# SETUP
# ---------------------
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOT_DIR)
CONFIG_PATH = os.path.join(BOT_DIR, "config.py")
SCALPER_STATE_FILE = os.path.join(BOT_DIR, "scalper_state.json")
SCALPER_STOP_FILE = SCALPER_STATE_FILE + ".stop"

st.set_page_config(
    page_title="POLYBOT",
    layout="wide",
    page_icon="https://polymarket.com/favicon.ico",
)

# ---------------------
# CUSTOM THEME / CSS
# ---------------------
st.markdown("""
<style>
/* === GLOBAL DARK THEME OVERRIDES === */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');

:root {
    --neon-green: #00ff88;
    --neon-red: #ff3366;
    --neon-blue: #00d4ff;
    --neon-purple: #a855f7;
    --neon-gold: #fbbf24;
    --bg-dark: #0a0a0f;
    --bg-card: #12121a;
    --bg-card-hover: #1a1a2e;
    --border-glow: rgba(0, 255, 136, 0.15);
    --text-primary: #e2e8f0;
    --text-secondary: #94a3b8;
}

/* Dark background */
.stApp, [data-testid="stAppViewContainer"], .main .block-container {
    background-color: var(--bg-dark) !important;
    color: var(--text-primary) !important;
}
[data-testid="stSidebar"] { background-color: #0d0d14 !important; }
[data-testid="stHeader"] { background-color: transparent !important; }

/* Metric cards — glassy look */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(18,18,26,0.9), rgba(26,26,46,0.7)) !important;
    border: 1px solid rgba(0, 255, 136, 0.1) !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    backdrop-filter: blur(10px) !important;
    transition: all 0.3s ease !important;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(0, 255, 136, 0.3) !important;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.08) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: var(--text-secondary) !important;
}
[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 1.5rem !important;
    color: var(--text-primary) !important;
}
[data-testid="stMetricDelta"] > div {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600 !important;
}

/* Tabs — sleek underline style */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px !important;
    background: transparent !important;
    border-bottom: 1px solid rgba(255,255,255,0.06) !important;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--text-secondary) !important;
    padding: 12px 24px !important;
    border: none !important;
    background: transparent !important;
    transition: all 0.2s ease !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--neon-green) !important; }
.stTabs [aria-selected="true"] {
    color: var(--neon-green) !important;
    border-bottom: 2px solid var(--neon-green) !important;
}

/* Buttons — neon glow */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #00ff88, #00cc6a) !important;
    color: #000 !important;
    font-weight: 700 !important;
    font-family: 'Inter', sans-serif !important;
    border: none !important;
    border-radius: 8px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.3) !important;
    transition: all 0.3s ease !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 0 30px rgba(0, 255, 136, 0.5) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    background: rgba(255, 51, 102, 0.15) !important;
    color: var(--neon-red) !important;
    border: 1px solid rgba(255, 51, 102, 0.3) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}

/* Expanders — dark glass */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] details summary {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
}

/* Dataframes — dark theme */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
}

/* Dividers */
hr { border-color: rgba(255,255,255,0.06) !important; }

/* Selectbox / inputs — dark */
[data-baseweb="select"] > div,
[data-baseweb="input"] > div {
    background: var(--bg-card) !important;
    border-color: rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}

/* Code blocks */
.stCodeBlock { border-radius: 12px !important; }

/* Strategy cards custom classes */
.strat-card {
    background: linear-gradient(135deg, var(--bg-card), var(--bg-card-hover));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 24px;
    position: relative;
    overflow: hidden;
}
.strat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--neon-green), var(--neon-blue));
}
.strat-card.kelly::before { background: linear-gradient(90deg, var(--neon-purple), var(--neon-blue)); }
.strat-card.aggressive::before { background: linear-gradient(90deg, var(--neon-red), var(--neon-gold)); }

/* Hero banner */
.hero-title {
    font-family: 'Inter', sans-serif;
    font-weight: 900;
    font-size: 2.2rem;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #00ff88, #00d4ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    line-height: 1.1;
}
.hero-subtitle {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 0.85rem;
    color: var(--text-secondary);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-top: 4px;
}
.hero-pnl-positive {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 1.8rem;
    color: var(--neon-green);
    text-shadow: 0 0 20px rgba(0, 255, 136, 0.4);
}
.hero-pnl-negative {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 1.8rem;
    color: var(--neon-red);
    text-shadow: 0 0 20px rgba(255, 51, 102, 0.4);
}

/* Pulse animation for live indicator */
@keyframes pulse-green {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0, 255, 136, 0.4); }
    50% { box-shadow: 0 0 0 8px rgba(0, 255, 136, 0); }
}
@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255, 51, 102, 0.4); }
    50% { box-shadow: 0 0 0 8px rgba(255, 51, 102, 0); }
}
.live-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
}
.live-dot.green { background: var(--neon-green); animation: pulse-green 2s infinite; }
.live-dot.red { background: var(--neon-red); animation: pulse-red 1.5s infinite; }

/* Win/loss badges */
.badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.05em; }
.badge-win { background: rgba(0, 255, 136, 0.15); color: var(--neon-green); border: 1px solid rgba(0, 255, 136, 0.3); }
.badge-loss { background: rgba(255, 51, 102, 0.15); color: var(--neon-red); border: 1px solid rgba(255, 51, 102, 0.3); }
.badge-hold { background: rgba(0, 212, 255, 0.15); color: var(--neon-blue); border: 1px solid rgba(0, 212, 255, 0.3); }

/* Rank badges */
.rank-badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 700; font-family: 'Inter', sans-serif;
    text-transform: uppercase; letter-spacing: 0.08em;
}
.rank-1 { background: linear-gradient(135deg, #fbbf24, #f59e0b); color: #000; box-shadow: 0 0 12px rgba(251, 191, 36, 0.4); }
.rank-2 { background: linear-gradient(135deg, #94a3b8, #64748b); color: #000; }
.rank-3 { background: linear-gradient(135deg, #b45309, #92400e); color: #fff; }

/* Streak counter */
.streak { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.85rem; }
.streak-hot { color: var(--neon-green); text-shadow: 0 0 8px rgba(0,255,136,0.3); }
.streak-cold { color: var(--neon-red); }

/* Progress bar for win rate */
.winrate-bar {
    height: 6px; border-radius: 3px; background: rgba(255,255,255,0.06);
    overflow: hidden; margin-top: 4px;
}
.winrate-fill {
    height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, var(--neon-green), var(--neon-blue));
    transition: width 0.5s ease;
}

/* Timer — countdown feel */
.countdown {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 1.4rem;
    padding: 8px 16px;
    border-radius: 8px;
    display: inline-block;
}
.countdown-safe { color: var(--neon-green); background: rgba(0,255,136,0.08); border: 1px solid rgba(0,255,136,0.15); }
.countdown-warn { color: var(--neon-gold); background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.15); }
.countdown-danger { color: var(--neon-red); background: rgba(255,51,102,0.08); border: 1px solid rgba(255,51,102,0.15); animation: pulse-red 1s infinite; }

/* Alert banners */
.alert-live {
    background: linear-gradient(135deg, rgba(255,51,102,0.1), rgba(255,51,102,0.05));
    border: 1px solid rgba(255,51,102,0.3);
    border-radius: 12px;
    padding: 16px 24px;
    font-family: 'Inter', sans-serif;
}
.alert-paper {
    background: linear-gradient(135deg, rgba(0,255,136,0.08), rgba(0,212,255,0.05));
    border: 1px solid rgba(0,255,136,0.2);
    border-radius: 12px;
    padding: 16px 24px;
    font-family: 'Inter', sans-serif;
}

/* Hide default streamlit branding */
#MainMenu, footer, header[data-testid="stHeader"] > div:first-child { visibility: hidden; }

/* === ARENA GAMIFICATION === */
@keyframes glow-pulse {
    0%, 100% { box-shadow: 0 0 15px rgba(0, 255, 136, 0.2); }
    50% { box-shadow: 0 0 30px rgba(0, 255, 136, 0.4), 0 0 60px rgba(0, 255, 136, 0.1); }
}
@keyframes trophy-shine {
    0% { text-shadow: 0 0 10px rgba(251, 191, 36, 0.3); }
    50% { text-shadow: 0 0 25px rgba(251, 191, 36, 0.8), 0 0 50px rgba(251, 191, 36, 0.3); }
    100% { text-shadow: 0 0 10px rgba(251, 191, 36, 0.3); }
}
@keyframes slide-in {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.arena-status-banner {
    background: linear-gradient(135deg, rgba(0,255,136,0.06), rgba(0,212,255,0.04));
    border: 1px solid rgba(0,255,136,0.2);
    border-radius: 16px;
    padding: 20px 28px;
    margin-bottom: 20px;
    animation: glow-pulse 3s ease-in-out infinite;
}
.arena-status-banner.stopped {
    background: linear-gradient(135deg, rgba(100,100,120,0.06), rgba(100,100,120,0.04));
    border-color: rgba(100,100,120,0.2);
    animation: none;
}
.arena-status-banner.finished {
    background: linear-gradient(135deg, rgba(251,191,36,0.06), rgba(245,158,11,0.04));
    border-color: rgba(251,191,36,0.2);
    animation: none;
}

.podium-card {
    background: linear-gradient(135deg, var(--bg-card), var(--bg-card-hover));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    padding: 20px;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: all 0.3s ease;
    animation: slide-in 0.5s ease-out;
}
.podium-card:hover {
    border-color: rgba(0,255,136,0.2);
    transform: translateY(-2px);
}
.podium-card.gold {
    border-color: rgba(251,191,36,0.3);
    box-shadow: 0 0 30px rgba(251,191,36,0.1);
}
.podium-card.gold::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; background: linear-gradient(90deg, #fbbf24, #f59e0b);
}
.podium-card.silver { border-color: rgba(148,163,184,0.3); }
.podium-card.silver::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; background: linear-gradient(90deg, #94a3b8, #cbd5e1);
}
.podium-card.bronze { border-color: rgba(180,83,9,0.3); }
.podium-card.bronze::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0;
    height: 3px; background: linear-gradient(90deg, #b45309, #d97706);
}

.trophy-icon {
    font-size: 2rem;
    margin-bottom: 4px;
}
.trophy-gold { animation: trophy-shine 2s ease-in-out infinite; }

.leaderboard-row {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-radius: 12px;
    margin-bottom: 4px;
    transition: all 0.2s ease;
    background: rgba(18,18,26,0.6);
    border: 1px solid rgba(255,255,255,0.03);
}
.leaderboard-row:hover {
    background: rgba(26,26,46,0.8);
    border-color: rgba(0,255,136,0.1);
}
.leaderboard-row.top-row {
    background: rgba(251,191,36,0.05);
    border-color: rgba(251,191,36,0.15);
}

.lb-rank {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 800;
    font-size: 1rem;
    width: 40px;
    text-align: center;
}
.lb-name {
    font-family: 'Inter', sans-serif;
    font-weight: 700;
    font-size: 0.9rem;
    color: #e2e8f0;
    flex: 1;
    min-width: 100px;
}
.lb-cat {
    font-family: 'Inter', sans-serif;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    margin-left: 8px;
}
.lb-cat-crypto { background: rgba(0,212,255,0.1); color: #00d4ff; }
.lb-cat-general { background: rgba(168,85,247,0.1); color: #a855f7; }
.lb-balance {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 0.95rem;
    width: 100px;
    text-align: right;
}
.lb-pnl {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    font-size: 0.85rem;
    width: 80px;
    text-align: right;
}
.lb-stats {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #64748b;
    width: 120px;
    text-align: right;
}
.lb-status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    margin-left: 8px;
}
.lb-status-open { background: #00ff88; box-shadow: 0 0 6px rgba(0,255,136,0.5); }
.lb-status-idle { background: #334155; }

.arena-elapsed {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: #00d4ff;
    letter-spacing: 0.05em;
}
</style>
""", unsafe_allow_html=True)

# ---------------------
# HELPER FUNCTIONS
# ---------------------

def load_config():
    """Load fresh config values."""
    import config
    importlib.reload(config)
    return config


def update_config(var_name, new_value):
    """Update a single variable in config.py, preserving inline comments."""
    with open(CONFIG_PATH, "r") as f:
        content = f.read()

    if isinstance(new_value, bool):
        val_str = "True" if new_value else "False"
    elif isinstance(new_value, float):
        val_str = f"{new_value:.2f}"
    elif isinstance(new_value, int):
        val_str = str(new_value)
    elif isinstance(new_value, str):
        val_str = f'"{new_value}"'
    else:
        val_str = repr(new_value)

    pattern = rf'^({re.escape(var_name)}\s*=\s*)([^\n#]+)(#.*)?$'

    def replacer(match):
        prefix = match.group(1)
        comment = match.group(3) or ""
        new_line = f"{prefix}{val_str}"
        if comment:
            new_line = f"{new_line.ljust(40)}{comment}"
        return new_line

    new_content = re.sub(pattern, replacer, content, flags=re.MULTILINE)

    with open(CONFIG_PATH, "w") as f:
        f.write(new_content)


def load_bets_df():
    """Load bets from CSV into a DataFrame."""
    from tracker import TRACKER_FILE, TRACKER_FIELDS

    if not os.path.exists(TRACKER_FILE):
        return pd.DataFrame(columns=TRACKER_FIELDS)

    for attempt in range(3):
        try:
            df = pd.read_csv(TRACKER_FILE)
            for col in ["price", "amount", "shares", "forecast_prob", "pnl"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            return df
        except PermissionError:
            time.sleep(0.5)

    return pd.DataFrame(columns=TRACKER_FIELDS)


def get_stats():
    """Get performance stats from tracker."""
    from tracker import calculate_stats
    return calculate_stats()


def run_bot(flag=None):
    """Run bot.py as a subprocess."""
    bot_path = os.path.join(BOT_DIR, "bot.py")
    cmd = [sys.executable, bot_path]
    if flag:
        cmd.append(flag)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=300, cwd=BOT_DIR,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Bot scan timed out (5 min limit)."
    except Exception as e:
        return False, "", str(e)


# --- Scalper subprocess management ---

def start_scalper(duration, market_type="5min", coin="btc"):
    """Launch scalper as a background subprocess."""
    runner = os.path.join(BOT_DIR, "scalper_runner.py")

    # Remove old stop signal and old state file for clean start
    for f in [SCALPER_STOP_FILE, SCALPER_STATE_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    proc = subprocess.Popen(
        [sys.executable, runner,
         "--duration", str(duration),
         "--state-file", SCALPER_STATE_FILE,
         "--market-type", market_type,
         "--coin", coin],
        cwd=BOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    st.session_state["scalper_pid"] = proc.pid
    st.session_state["scalper_running"] = True


def stop_scalper():
    """Stop the running scalper via stop signal file + process kill."""
    # Write stop signal file
    try:
        with open(SCALPER_STOP_FILE, "w") as f:
            f.write("stop")
    except OSError:
        pass
    # Force kill the process for instant stop
    pid = st.session_state.get("scalper_pid")
    if pid:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=5)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    st.session_state["scalper_running"] = False
    st.session_state["scalper_pid"] = None


def is_scalper_running():
    """Check if scalper process is still alive."""
    pid = st.session_state.get("scalper_pid")
    if not pid:
        return False
    try:
        if sys.platform == "win32":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                    capture_output=True, text=True, timeout=5)
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def read_scalper_state():
    """Read the latest state from the JSON file."""
    if not os.path.exists(SCALPER_STATE_FILE):
        return None
    try:
        with open(SCALPER_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError):
        return None


# --- Live BTC/Market data (independent of scalper subprocess) ---

BINANCE_API = "https://api.binance.com/api/v3"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


# Coin -> Binance symbol
COIN_SYMBOLS = {"btc": "BTCUSDT", "eth": "ETHUSDT", "sol": "SOLUSDT", "doge": "DOGEUSDT"}
COIN_LABELS = {"btc": "BTC", "eth": "ETH", "sol": "SOL", "doge": "DOGE"}
COIN_COLORS = {"btc": "#f7931a", "eth": "#627eea", "sol": "#9945ff", "doge": "#c2a633"}

# Slug patterns per coin
COIN_SLUG_PATTERNS = {
    "btc": {"5min": ("btc-updown-5m-{}", 300), "15min": ("btc-updown-15m-{}", 900)},
    "eth": {"5min": ("eth-updown-5m-{}", 300), "15min": ("eth-updown-15m-{}", 900)},
}


@st.cache_data(ttl=5)
def fetch_crypto_24h(coin="btc"):
    """Fetch 24h stats from Binance for any coin."""
    symbol = COIN_SYMBOLS.get(coin.lower(), f"{coin.upper()}USDT")
    try:
        resp = requests.get(
            f"{BINANCE_API}/ticker/24hr",
            params={"symbol": symbol},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "price": float(data["lastPrice"]),
            "change_pct": float(data["priceChangePercent"]),
            "high": float(data["highPrice"]),
            "low": float(data["lowPrice"]),
            "volume": float(data["quoteVolume"]),
        }
    except Exception:
        return None


@st.cache_data(ttl=8)
def fetch_current_market(coin="btc", market_type="5min"):
    """Fetch the current Up/Down market with live CLOB prices."""
    import time as _time
    coin = coin.lower()
    patterns = COIN_SLUG_PATTERNS.get(coin, COIN_SLUG_PATTERNS.get("btc", {}))
    pattern, interval = patterns.get(market_type, patterns.get("5min", ("btc-updown-5m-{}", 300)))
    now = int(_time.time())
    window_ts = (now // interval) * interval
    slug = pattern.format(window_ts)
    time_remaining = window_ts + interval - now

    try:
        resp = requests.get(
            f"{GAMMA_API_URL}/events",
            params={"slug": slug},
            timeout=10,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception:
        return None

    if not events:
        return None

    event = events[0]
    markets = event.get("markets", [])
    if not markets:
        return None

    market = markets[0]
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
        gamma_prices = json.loads(market.get("outcomePrices", "[]"))
    except (json.JSONDecodeError, TypeError):
        return None

    if len(outcomes) < 2 or len(token_ids) < 2 or len(gamma_prices) < 2:
        return None

    # Fetch real-time CLOB prices
    up_price, down_price = float(gamma_prices[0]), float(gamma_prices[1])
    for i, label in enumerate(["up", "down"]):
        try:
            r = requests.get(
                f"{CLOB_API_URL}/midpoint",
                params={"token_id": token_ids[i]},
                timeout=5,
            )
            r.raise_for_status()
            mid = float(r.json().get("mid", 0))
            if mid > 0:
                if label == "up":
                    up_price = mid
                else:
                    down_price = mid
        except Exception:
            pass

    return {
        "title": event.get("title", ""),
        "slug": slug,
        "up_price": up_price,
        "down_price": down_price,
        "gamma_up": float(gamma_prices[0]),
        "gamma_down": float(gamma_prices[1]),
        "time_remaining": time_remaining,
        "window_end": window_ts + interval,
        "accepting_orders": market.get("acceptingOrders", False),
    }


@st.cache_data(ttl=10)
def fetch_crypto_klines(coin="btc", minutes=30):
    """Fetch 1-minute candles for mini chart."""
    symbol = COIN_SYMBOLS.get(coin.lower(), f"{coin.upper()}USDT")
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={"symbol": symbol, "interval": "1m", "limit": minutes},
            timeout=5,
        )
        resp.raise_for_status()
        return [
            {"time": k[0], "close": float(k[4])}
            for k in resp.json()
        ]
    except Exception:
        return []


# ---------------------
# LOAD DATA
# ---------------------
cfg = load_config()
df = load_bets_df()
stats = get_stats()

from strategy import get_bankroll_split
split = get_bankroll_split()


# ---------------------
# HEADER — Hero Banner
# ---------------------
h1, h2, h3 = st.columns([3, 2, 1])
with h1:
    st.markdown('<p class="hero-title">POLYBOT</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-subtitle">Polymarket Trading Terminal</p>', unsafe_allow_html=True)
with h2:
    if cfg.DRY_RUN:
        st.markdown(
            '<div class="alert-paper">'
            '<span class="live-dot green"></span>'
            '<strong>PAPER MODE</strong> &mdash; simulated trades, no real money'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="alert-live">'
            '<span class="live-dot red"></span>'
            '<strong>LIVE TRADING</strong> &mdash; real money on the line'
            '</div>',
            unsafe_allow_html=True,
        )
with h3:
    now_str = datetime.now().strftime("%H:%M:%S")
    st.markdown(
        f'<div style="text-align:right;padding-top:8px;">'
        f'<span style="font-family:JetBrains Mono,monospace;color:var(--text-secondary);font-size:0.8rem;">{now_str}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------
# TABS
# ---------------------
tab_arena, tab_whales, tab2, tab6, tab1, tab3, tab4, tab5, tab_info = st.tabs([
    "Arena", "Whale Tracker", "Scalper", "Trending Bets", "Overview", "Settings", "Simulation", "History", "Info"
])


# =============================================
# TAB: ARENA (10-Strategy Competition)
# =============================================
ARENA_STATE_FILE_PATH = os.path.join(BOT_DIR, "arena_state.json")
ARENA_STOP_FILE_PATH = ARENA_STATE_FILE_PATH + ".stop"


def read_arena_state():
    """Read arena state from JSON."""
    if not os.path.exists(ARENA_STATE_FILE_PATH):
        return None
    try:
        with open(ARENA_STATE_FILE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError):
        return None


def is_arena_running():
    """Check if arena process is alive (works on Windows + Unix)."""
    arena_state = read_arena_state()
    if not arena_state:
        return False
    if arena_state.get("status") == "finished":
        return False
    # Check if state file was updated recently (within 30s = alive)
    try:
        mtime = os.path.getmtime(ARENA_STATE_FILE_PATH)
        age = time.time() - mtime
        if age < 30:
            return True
    except OSError:
        pass
    # Fallback: check PID via tasklist on Windows
    pid = arena_state.get("pid")
    if pid:
        try:
            if sys.platform == "win32":
                import subprocess as sp
                result = sp.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except Exception:
            pass
    return False


def start_arena(duration_min, coin="btc"):
    """Launch arena as background subprocess."""
    runner = os.path.join(BOT_DIR, "arena_runner.py")
    for f in [ARENA_STOP_FILE_PATH, ARENA_STATE_FILE_PATH]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    proc = subprocess.Popen(
        [sys.executable, runner, "--duration", str(duration_min), "--coin", coin],
        cwd=BOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    st.session_state["arena_pid"] = proc.pid
    st.session_state["arena_running"] = True


def stop_arena():
    """Stop arena via stop signal file + kill process + update state."""
    # Write stop file for graceful shutdown
    try:
        with open(ARENA_STOP_FILE_PATH, "w") as f:
            f.write("stop")
    except OSError:
        pass
    # Kill the process directly for immediate stop
    arena_state = read_arena_state()
    if arena_state:
        pid = arena_state.get("pid")
        if pid:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True, timeout=5)
                else:
                    import signal
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        # Mark state as finished immediately so dashboard reflects it
        arena_state["status"] = "finished"
        try:
            with open(ARENA_STATE_FILE_PATH, "w") as f:
                json.dump(arena_state, f, indent=2)
        except OSError:
            pass
    st.session_state["arena_running"] = False


def _calc_streak(trades_list):
    """Calculate current win/loss streak."""
    streak = 0
    streak_type = ""
    for t in reversed(trades_list):
        if not streak_type:
            streak_type = "W" if t.get("pnl", 0) > 0 else "L"
            streak = 1
        elif (streak_type == "W" and t.get("pnl", 0) > 0) or (streak_type == "L" and t.get("pnl", 0) <= 0):
            streak += 1
        else:
            break
    return streak, streak_type


def _format_elapsed(start_str):
    """Format elapsed time from session ID (YYYYMMDD_HHMMSS)."""
    try:
        start = datetime.strptime(start_str, "%Y%m%d_%H%M%S")
        elapsed = datetime.now() - start
        total_s = int(elapsed.total_seconds())
        if total_s < 0:
            return "0s"
        hours, remainder = divmod(total_s, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    except (ValueError, TypeError):
        return "?"


with tab_arena:
    # Detect arena status from state file (not session state — survives page refresh)
    arena_running = is_arena_running()
    arena_state = read_arena_state()
    arena_finished = arena_state and arena_state.get("status") == "finished" and not arena_running

    # ==========================================
    # STATUS BANNER — Always visible at top
    # ==========================================
    if arena_running and arena_state:
        session_id = arena_state.get("session_id", "")
        elapsed = _format_elapsed(session_id)
        coin = arena_state.get("coin", "btc").upper()
        price = arena_state.get("crypto_price", 0)
        n_strats = len(arena_state.get("strategies", {}))
        total_trades = sum(s.get("summary", {}).get("total_trades", 0) for s in arena_state.get("strategies", {}).values())

        # Market countdown
        mkt = arena_state.get("market", {})
        mkt_remaining = mkt.get("time_remaining", 0)
        mkt_title = mkt.get("title", "")
        cd_mins, cd_secs = divmod(max(0, int(mkt_remaining)), 60)
        if mkt_remaining < 60:
            cd_class = "countdown-danger"
        elif mkt_remaining < 120:
            cd_class = "countdown-warn"
        else:
            cd_class = "countdown-safe"
        countdown_html = f'<span class="countdown {cd_class}" style="font-size:1.1rem;padding:4px 12px;">{cd_mins}:{cd_secs:02d}</span>' if mkt_remaining > 0 else ""

        st.markdown(
            f'<div class="arena-status-banner">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span class="live-dot green"></span>'
            f'<span style="font-family:Inter,sans-serif;font-weight:800;font-size:1.1rem;color:#00ff88;text-transform:uppercase;letter-spacing:0.05em;">Arena Running</span>'
            f'<span class="arena-elapsed">{elapsed} elapsed</span>'
            f'</div>'
            f'<div style="display:flex;gap:16px;align-items:center;">'
            f'{countdown_html}'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:#94a3b8;">{coin} ${price:,.2f}</span>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:#64748b;">{n_strats} strats | {total_trades} trades</span>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
    elif arena_finished and arena_state:
        session_id = arena_state.get("session_id", "")
        total_trades = sum(s.get("summary", {}).get("total_trades", 0) for s in arena_state.get("strategies", {}).values())
        st.markdown(
            f'<div class="arena-status-banner finished">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<span style="font-size:1.5rem;">&#127942;</span>'
            f'<span style="font-family:Inter,sans-serif;font-weight:800;font-size:1.1rem;color:#fbbf24;text-transform:uppercase;letter-spacing:0.05em;">Arena Finished</span>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:0.8rem;color:#94a3b8;">Session {session_id} | {total_trades} trades</span>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="arena-status-banner stopped">'
            '<div style="display:flex;align-items:center;gap:12px;">'
            '<span style="font-size:1.2rem;color:#4a5568;">&#9679;</span>'
            '<span style="font-family:Inter,sans-serif;font-weight:700;font-size:1rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">Arena Idle</span>'
            '<span style="font-family:JetBrains Mono,monospace;font-size:0.75rem;color:#4a5568;">Configure and start below</span>'
            '</div></div>',
            unsafe_allow_html=True,
        )

    # ==========================================
    # CONTROLS — Start/Stop + Config
    # ==========================================
    ac1, ac2, ac3 = st.columns([1, 1, 1])
    with ac1:
        arena_duration = st.number_input("Duration (hours)", value=12, min_value=1, max_value=48, step=1, key="arena_dur")
    with ac2:
        arena_coin = st.selectbox("Coin", ["BTC", "ETH"], key="arena_coin").lower()
    with ac3:
        st.markdown('<div style="height:28px;"></div>', unsafe_allow_html=True)  # spacer to align with inputs
        if not arena_running:
            if st.button("START ARENA", type="primary", use_container_width=True):
                start_arena(arena_duration * 60, arena_coin)
                st.rerun()
        else:
            if st.button("STOP ARENA", type="secondary", use_container_width=True):
                stop_arena()
                time.sleep(1)
                st.rerun()

    st.divider()

    # ==========================================
    # LEADERBOARD — Main content
    # ==========================================
    if arena_state and (arena_running or arena_finished):
        arena_strategies = arena_state.get("strategies", {})

        if arena_strategies:
            # Build ranked list
            ranked = []
            for sname, sdata in arena_strategies.items():
                sm = sdata.get("summary", {})
                bal = sm.get("balance", 100.0)
                pos = sdata.get("position")
                display_bal = bal
                if pos:
                    display_bal += pos.get("cost", 0) + pos.get("current_pnl", 0)
                pnl = display_bal - 100.0
                trades_list = sdata.get("trades", [])
                streak, streak_type = _calc_streak(trades_list)
                ranked.append({
                    "name": sname,
                    "display_name": sdata.get("display_name", sname),
                    "category": sdata.get("category", ""),
                    "balance": display_bal,
                    "pnl": pnl,
                    "trades": sm.get("total_trades", 0),
                    "wins": sm.get("wins", 0),
                    "losses": sm.get("losses", 0),
                    "win_rate": sm.get("win_rate", 0),
                    "roi": sm.get("roi", 0),
                    "position": pos,
                    "sdata": sdata,
                    "streak": streak,
                    "streak_type": streak_type,
                })
            ranked.sort(key=lambda x: x["pnl"], reverse=True)

            # === TITLE ===
            st.markdown(
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">'
                '<span style="font-family:Inter,sans-serif;font-weight:900;font-size:1.6rem;'
                'background:linear-gradient(135deg,#fbbf24,#f59e0b,#00ff88);-webkit-background-clip:text;'
                '-webkit-text-fill-color:transparent;background-clip:text;">'
                'STRATEGY ARENA</span>'
                '<span style="font-family:JetBrains Mono,monospace;font-size:0.75rem;color:#64748b;">'
                f'{len(ranked)} strategies competing</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            # === UNIFIED LEADERBOARD — styled HTML rows, click to expand trades ===
            rank_colors = {1: "#fbbf24", 2: "#94a3b8", 3: "#b45309"}
            rank_emojis = {1: "&#127942;", 2: "&#129352;", 3: "&#129353;"}
            rank_labels_map = {1: "1ST", 2: "2ND", 3: "3RD"}

            for i, r in enumerate(ranked):
                rank = i + 1
                r_color = rank_colors.get(rank, "#4a5568")
                pnl_color = "#00ff88" if r["pnl"] >= 0 else "#ff3366"
                pnl_sign = "+" if r["pnl"] >= 0 else ""
                wr_str = f'{int(r["win_rate"]*100)}%' if r["trades"] > 0 else "-"
                rank_display = rank_emojis.get(rank, f'#{rank}')
                pos_dot = "lb-status-open" if r["position"] else "lb-status-idle"
                row_cls = "leaderboard-row top-row" if rank <= 3 else "leaderboard-row"
                streak_html = ""
                if r["streak"] > 0:
                    s_color = "#00ff88" if r["streak_type"] == "W" else "#ff3366"
                    streak_html = f'<span style="font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.85rem;color:{s_color};margin-left:10px;">{r["streak_type"]}{r["streak"]}</span>'
                pos_badge = ""
                ko_badge = ""
                if r["balance"] <= 0:
                    ko_badge = '<span style="font-family:JetBrains Mono,monospace;font-weight:900;font-size:0.85rem;color:#ff3366;margin-left:10px;background:rgba(255,51,102,0.15);padding:2px 8px;border-radius:4px;border:1px solid rgba(255,51,102,0.3);animation:glow-pulse 1.5s infinite;">KO</span>'
                if r["position"]:
                    pos_pnl = r["position"].get("current_pnl", 0)
                    pb_color = "#00ff88" if pos_pnl >= 0 else "#ff3366"
                    pos_badge = f'<span style="font-family:JetBrains Mono,monospace;font-size:0.75rem;color:{pb_color};margin-left:10px;">OPEN {pos_pnl:+.2f}</span>'

                # Styled HTML row
                st.markdown(
                    f'<div class="{row_cls}" style="padding:14px 18px;">'
                    f'<div class="lb-rank" style="color:{r_color};font-size:1.2rem;width:50px;">{rank_display}</div>'
                    f'<div class="lb-name" style="font-size:1.05rem;">{r["display_name"]}{ko_badge}{streak_html}{pos_badge}</div>'
                    f'<div class="lb-balance" style="color:{pnl_color};font-size:1.15rem;width:120px;">${r["balance"]:.2f}</div>'
                    f'<div class="lb-pnl" style="color:{pnl_color};font-size:1rem;width:90px;">{pnl_sign}${abs(r["pnl"]):.2f}</div>'
                    f'<div class="lb-stats" style="font-size:0.85rem;width:130px;">{r["trades"]}T | {wr_str} WR</div>'
                    f'<div class="lb-status-dot {pos_dot}"></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Expandable trade details right below the row
                sdata = r["sdata"]
                trades_list = sdata.get("trades", [])
                log_lines = sdata.get("log", [])
                rank_label = rank_labels_map.get(rank, f"#{rank}")
                has_content = bool(trades_list) or bool(log_lines) or r["position"]

                if has_content:
                    with st.expander(f"View {r['display_name']} details", expanded=False):
                        # Open position
                        if r["position"]:
                            pos = r["position"]
                            pos_pnl = pos.get("current_pnl", 0)
                            pos_color = "#00ff88" if pos_pnl >= 0 else "#ff3366"
                            st.markdown(
                                f'<div style="background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.15);border-radius:8px;padding:10px 14px;margin-bottom:12px;font-family:JetBrains Mono,monospace;font-size:0.8rem;">'
                                f'<span style="color:#00d4ff;font-weight:700;">OPEN </span>'
                                f'<span style="color:#e2e8f0;">{pos.get("side","")} {pos.get("shares",0):.1f}sh @ ${pos.get("entry_price",0):.3f}</span>'
                                f'<span style="color:{pos_color};font-weight:700;margin-left:12px;">P&L: {pos_pnl:+.2f}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                        # Trade history
                        if trades_list:
                            tdf = pd.DataFrame(trades_list)
                            tdf["result"] = tdf["pnl"].apply(lambda x: "WIN" if x > 0 else "LOSS")
                            display_cols = [c for c in ["side", "entry_price", "exit_price", "shares", "cost", "pnl", "result", "exit_type"] if c in tdf.columns]

                            def _color_pnl_arena(val):
                                try:
                                    return f"color: {'#00ff88' if val > 0 else '#ff3366' if val < 0 else '#64748b'}"
                                except (ValueError, TypeError):
                                    return ""

                            pnl_cols = [c for c in ["pnl"] if c in display_cols]
                            styled_trades = tdf[display_cols].style.map(_color_pnl_arena, subset=pnl_cols)
                            st.dataframe(styled_trades, use_container_width=True, hide_index=True)

                        # Activity log
                        if log_lines:
                            log_html = '<div style="background:#0a0a0f;border:1px solid rgba(0,255,136,0.08);border-radius:8px;padding:12px;font-family:JetBrains Mono,monospace;font-size:0.7rem;max-height:200px;overflow-y:auto;margin-top:8px;">'
                            for line in log_lines[-15:]:
                                if "ENTER" in line:
                                    lc = "#00d4ff"
                                elif "EXIT" in line and ("profit" in line.lower() or "P&L $+" in line):
                                    lc = "#00ff88"
                                elif "EXIT" in line or "LOSS" in line:
                                    lc = "#ff3366"
                                elif "SKIP" in line:
                                    lc = "#64748b"
                                else:
                                    lc = "#94a3b8"
                                log_html += f'<div style="color:{lc};padding:1px 0;">{line}</div>'
                            log_html += '</div>'
                            st.markdown(log_html, unsafe_allow_html=True)

            # === EVENT LOG ===
            arena_log = arena_state.get("log", [])
            if arena_log:
                with st.expander("Arena Event Log", expanded=arena_running):
                    log_html = '<div style="background:#0d0d14;border:1px solid rgba(0,255,136,0.1);border-radius:12px;padding:16px;font-family:JetBrains Mono,monospace;font-size:0.72rem;max-height:400px;overflow-y:auto;">'
                    for line in arena_log[-50:]:
                        if "ENTER" in line or "WIN" in line or "profit" in line.lower():
                            color = "#00ff88"
                        elif "LOSS" in line or "ERROR" in line or "stop_loss" in line:
                            color = "#ff3366"
                        elif "SIGNAL" in line or "ARB" in line or "Tick" in line:
                            color = "#00d4ff"
                        elif "STARTED" in line or "BTC" in line:
                            color = "#a855f7"
                        else:
                            color = "#4a5568"
                        log_html += f'<div style="color:{color};padding:1px 0;">{line}</div>'
                    log_html += '</div>'
                    st.markdown(log_html, unsafe_allow_html=True)

            # === TRADE HISTORY (all sessions) ===
            st.divider()
            with st.expander("Arena Trade History (all sessions)", expanded=False):
                from arena import load_arena_trades
                all_arena_trades = load_arena_trades()
                if all_arena_trades:
                    adf = pd.DataFrame(all_arena_trades)
                    for nc in ["cost", "pnl", "pnl_pct", "entry_price", "exit_price", "shares", "edge", "hold_duration_s"]:
                        if nc in adf.columns:
                            adf[nc] = pd.to_numeric(adf[nc], errors="coerce")

                    ahc1, ahc2, ahc3 = st.columns(3)
                    ahc1.metric("Total Trades", len(adf))
                    ahc2.metric("Total P&L", f"${adf['pnl'].sum():+.2f}")
                    ahc3.metric("Sessions", adf["session_id"].nunique() if "session_id" in adf.columns else "?")

                    strat_filter = st.selectbox(
                        "Filter by strategy", ["All"] + sorted(adf["strategy"].dropna().unique().tolist()),
                        key="arena_hist_filter",
                    )
                    if strat_filter != "All":
                        adf = adf[adf["strategy"] == strat_filter]

                    show_cols = [c for c in [
                        "timestamp", "strategy", "side", "entry_price", "exit_price",
                        "cost", "pnl", "exit_type", "title",
                    ] if c in adf.columns]

                    st.dataframe(adf[show_cols].tail(50), use_container_width=True, hide_index=True)
                    st.download_button("Download Arena Trades (CSV)", adf.to_csv(index=False), "arena_trades_export.csv", "text/csv")
                else:
                    st.info("No arena trade history yet. Start the arena to begin collecting data.")

    else:
        # Arena idle — simple prompt
        st.markdown(
            '<div style="background:var(--bg-card);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:24px;margin-top:8px;text-align:center;">'
            '<div style="font-family:Inter,sans-serif;font-weight:800;font-size:1.1rem;color:#e2e8f0;margin-bottom:8px;">No arena running</div>'
            '<div style="font-family:Inter,sans-serif;font-size:0.8rem;color:#64748b;">Set duration and click Start Arena above. See the Info tab for strategy details.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Auto-refresh when running
    if arena_running:
        time.sleep(5)
        st.rerun()


# =============================================
# TAB 1: OVERVIEW
# =============================================
with tab1:
    # KPI Metrics
    c1, c2, c3, c4, c5 = st.columns(5)

    total_pnl = stats["total_pnl"] if stats else 0
    current_bankroll = cfg.TOTAL_BANKROLL + total_pnl

    c1.metric("Bankroll", f"${current_bankroll:.2f}",
              delta=f"${total_pnl:+.2f}" if stats else None)
    c2.metric("ROI", f"{stats['roi']:+.1f}%" if stats else "N/A")
    c3.metric("Win Rate", f"{stats['hit_rate']:.0%}" if stats else "N/A")

    brier = stats.get("brier_score") if stats else None
    if brier is not None:
        quality = "good" if brier < 0.20 else "fair" if brier < 0.25 else "poor"
        c4.metric("Brier Score", f"{brier:.3f}", delta=quality)
    else:
        c4.metric("Brier Score", "N/A")

    c5.metric("Open Bets", stats["open_bets"] if stats else 0)

    # Bot output
    if st.session_state.get("last_output"):
        with st.expander("Last Bot Output", expanded=False):
            st.code(st.session_state["last_output"])

    # Charts
    st.subheader("Performance")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        resolved = df[df["pnl"].notna()] if not df.empty else pd.DataFrame()
        if not resolved.empty:
            resolved_sorted = resolved.sort_values("timestamp")
            resolved_sorted["cumulative_pnl"] = resolved_sorted["pnl"].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=resolved_sorted["timestamp"],
                y=resolved_sorted["cumulative_pnl"],
                mode="lines+markers", name="P&L",
                line=dict(color="#00cc96"),
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="#4a5568")
            fig.update_layout(
                title="Equity Curve (Cumulative P&L)",
                xaxis_title="Time", yaxis_title="P&L ($)",
                height=350, margin=dict(l=20, r=20, t=40, b=20),
                plot_bgcolor="#0a0a0f", paper_bgcolor="#0a0a0f",
                font_color="#94a3b8",
                xaxis=dict(gridcolor="rgba(255,255,255,0.04)", color="#4a5568"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.04)", color="#4a5568"),
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Equity curve will appear after bets resolve.")

    with chart_col2:
        if stats and stats.get("calibration_buckets"):
            buckets = stats["calibration_buckets"]
            predicted, actual, sizes = [], [], []
            for bucket, data in sorted(buckets.items()):
                if data["count"] > 0:
                    predicted.append(bucket)
                    actual.append(data["hits"] / data["count"])
                    sizes.append(data["count"])

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[0, 1], y=[0, 1], mode="lines", name="Perfect",
                line=dict(dash="dash", color="gray"),
            ))
            fig.add_trace(go.Scatter(
                x=predicted, y=actual, mode="markers+text", name="Actual",
                marker=dict(size=[s * 5 + 10 for s in sizes], color="#00d4ff"),
                text=[f"n={s}" for s in sizes], textposition="top center",
            ))
            fig.update_layout(
                title="Calibration (Predicted vs Actual)",
                xaxis_title="Predicted Probability", yaxis_title="Actual Hit Rate",
                height=350, margin=dict(l=20, r=20, t=40, b=20),
                plot_bgcolor="#0a0a0f", paper_bgcolor="#0a0a0f",
                font_color="#94a3b8",
                xaxis=dict(gridcolor="rgba(255,255,255,0.04)", color="#4a5568"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.04)", color="#4a5568"),
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Calibration plot requires resolved bets with forecasts.")

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        labels = ["Weather", "Longshot"]
        values = [split["weather"], split["longshot"]]
        if split.get("short_term", 0) > 0:
            labels.append("Short-Term")
            values.append(split["short_term"])
        fig = px.pie(
            names=labels, values=values, title="Bankroll Allocation", hole=0.4,
            color_discrete_sequence=["#00ff88", "#00d4ff", "#a855f7", "#fbbf24"],
        )
        fig.update_layout(
            height=350, margin=dict(l=20, r=20, t=40, b=20),
            plot_bgcolor="#0a0a0f", paper_bgcolor="#0a0a0f",
            font_color="#94a3b8",
        )
        st.plotly_chart(fig, width="stretch")

    with chart_col4:
        if not df.empty and "category" in df.columns:
            cat_df = df.dropna(subset=["category"])
            if not cat_df.empty:
                cat_summary = cat_df.groupby("category").agg(
                    risked=("amount", "sum"), pnl=("pnl", "sum"), count=("amount", "count"),
                ).reset_index()
                cat_summary["roi"] = (cat_summary["pnl"] / cat_summary["risked"] * 100).fillna(0)
                cat_summary = cat_summary.sort_values("risked", ascending=True)
                colors = ["#00cc96" if v >= 0 else "#ef553b" for v in cat_summary["roi"]]
                fig = go.Figure(go.Bar(
                    x=cat_summary["risked"], y=cat_summary["category"],
                    orientation="h", marker_color=colors,
                    text=[f"${r:.2f}" for r in cat_summary["risked"]], textposition="auto",
                ))
                fig.update_layout(
                    title="Risked by Category", xaxis_title="$ Risked",
                    height=350, margin=dict(l=20, r=20, t=40, b=20),
                    plot_bgcolor="#0a0a0f", paper_bgcolor="#0a0a0f",
                    font_color="#94a3b8",
                    xaxis=dict(gridcolor="rgba(255,255,255,0.04)", color="#4a5568"),
                    yaxis=dict(color="#4a5568"),
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Category breakdown will appear after bets are placed.")
        else:
            st.info("Category breakdown will appear after bets are placed.")

    # Strategy Cards
    st.subheader("Strategies")
    strategies = [
        ("Weather Grinder", "weather", True),
        ("Long Shot Scanner", "longshot", True),
        ("Short-Term Crypto", "short_term", cfg.SHORT_TERM_ENABLED),
        ("High-Prob Farming", "high_prob", cfg.HIGH_PROB_ENABLED),
        ("Structural Arbitrage", "arbitrage", cfg.ARBITRAGE_ENABLED),
        ("Live Scalper", "scalp", cfg.SCALP_ENABLED),
    ]

    for name, key, enabled in strategies:
        status_txt = "[ON]" if enabled else "[OFF]"
        with st.expander(f"{status_txt} {name}", expanded=False):
            if not enabled:
                st.warning(f"{name} is disabled.")
                continue

            strat_df = df[df["strategy"] == key] if not df.empty and "strategy" in df.columns else pd.DataFrame()
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Total Bets", len(strat_df))

            resolved_strat = strat_df[strat_df["pnl"].notna()] if not strat_df.empty else pd.DataFrame()
            wins = len(resolved_strat[resolved_strat["pnl"] > 0]) if not resolved_strat.empty else 0
            losses = len(resolved_strat) - wins
            sc2.metric("Wins / Losses", f"{wins} / {losses}")
            sc3.metric("P&L", f"${resolved_strat['pnl'].sum():+.2f}" if not resolved_strat.empty else "$0.00")
            sc4.metric("Risked", f"${strat_df['amount'].sum():.2f}" if not strat_df.empty else "$0.00")

            if not strat_df.empty:
                display_cols = [c for c in ["timestamp", "title", "side", "price", "amount", "status", "pnl"] if c in strat_df.columns]
                st.dataframe(
                    strat_df[display_cols].tail(5).sort_values("timestamp", ascending=False),
                    width="stretch", hide_index=True,
                )

    # Run scan buttons
    st.subheader("Run Scans")
    btn_cols = st.columns(6)
    scan_buttons = [
        ("Full Scan", None), ("Weather", "--weather"), ("Longshots", "--longshots"),
        ("Short-Term", "--short-term"), ("High-Prob", "--high-prob"), ("Arbitrage", "--arbitrage"),
    ]
    for col, (label, flag) in zip(btn_cols, scan_buttons):
        with col:
            if st.button(label, width="stretch"):
                with st.spinner(f"Running {label}..."):
                    ok, out, err = run_bot(flag)
                st.session_state["last_output"] = out if ok else err
                st.rerun()


# =============================================
# TAB: WHALE TRACKER
# =============================================

WHALE_REGISTRY = {
    "0x61276aba49117fd9299707d5d573652949d5c977": {
        "name": "MuseumOfBees", "pnl": "+$171K", "volume": "$31.7M",
        "style": "Crypto Scalper", "color": "#00ff88",
    },
    "0x970e744a34cd0795ff7b4ba844018f17b7fd5c26": {
        "name": "tugao9", "pnl": "+$18.9K", "volume": "$937K",
        "style": "Crypto Scalper", "color": "#00d4ff",
    },
    "0x2eb5714ff6f20f5f9f7662c556dbef5e1c9bf4d4": {
        "name": "Realistic-Swivel", "pnl": "+$125K", "volume": "$31M",
        "style": "Micro-Scalper", "color": "#a855f7",
    },
    "0x87650b9f63563f7c456d9bbcceee5f9faf06ed81": {
        "name": "2B9S", "pnl": "+$100K", "volume": "$12M",
        "style": "Sports/Weather/Longshots", "color": "#fbbf24",
    },
    "0xb2a3623364c33561d8312e1edb79eb941c798510": {
        "name": "aekghas", "pnl": "+$54K", "volume": "$704K",
        "style": "War/Geopolitical", "color": "#ff3366",
    },
    "0x96489abcb9f583d6835c8ef95ffc923d05a86825": {
        "name": "anoin123", "pnl": "-$4.87M", "volume": "$53.3M",
        "style": "Everything (Degen)", "color": "#ff6b35",
    },
    "0x1cc16713196d456f86fa9c7387dd326a7f73b8df": {
        "name": "Wickier", "pnl": "+$220K", "volume": "$12.6M",
        "style": "Diversified", "color": "#06d6a0",
    },
    "0x7744bfd749a70020d16a1fcbac1d064761c9999e": {
        "name": "chungguskhan", "pnl": "+$750K", "volume": "$63.8M",
        "style": "Geopolitical/Crypto", "color": "#e040fb",
    },
    "0xde7be6d489bce070a959e0cb813128ae659b5f4b": {
        "name": "wan123", "pnl": "+$360K", "volume": "$10.4M",
        "style": "Diversified Whale", "color": "#00bcd4",
    },
    "0x4d49acb0ae1c463eb5b1947d174141b812ba7450": {
        "name": "no1yet", "pnl": "+$34K", "volume": "N/A",
        "style": "Commodities/Macro", "color": "#8d6e63",
    },
    "0xad142563a8d80e3f6a18ca5fa5936027942bbf69": {
        "name": "myfirstpubes", "pnl": "+$56K", "volume": "N/A",
        "style": "Geopolitical", "color": "#ef5350",
    },
}

WHALE_DATA_API = "https://data-api.polymarket.com"


@st.cache_data(ttl=30)
def fetch_whale_activity(address, limit=20):
    """Fetch recent activity for a whale wallet."""
    try:
        resp = requests.get(
            f"{WHALE_DATA_API}/activity",
            params={"user": address, "limit": limit},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


@st.cache_data(ttl=60)
def fetch_whale_positions(address, limit=20):
    """Fetch current positions for a whale wallet."""
    try:
        resp = requests.get(
            f"{WHALE_DATA_API}/positions",
            params={"user": address, "limit": limit},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


with tab_whales:
    st.markdown(
        '<div style="font-family:Inter,sans-serif;font-weight:900;font-size:1.8rem;'
        'background:linear-gradient(135deg,#00ff88,#00d4ff,#a855f7);-webkit-background-clip:text;'
        '-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px;">'
        'WHALE TRACKER</div>'
        '<div style="font-family:Inter,sans-serif;font-size:0.85rem;color:#94a3b8;margin-bottom:20px;">'
        'Live tracking of 9 profitable Polymarket whales. See their trades, positions, and strategies in real-time.</div>',
        unsafe_allow_html=True,
    )

    # Whale selector
    whale_options = {f"{info['name']} ({info['pnl']})": addr for addr, info in WHALE_REGISTRY.items()}
    selected_label = st.selectbox(
        "Select Whale",
        list(whale_options.keys()),
        key="whale_select",
    )
    selected_addr = whale_options[selected_label]
    whale_info = WHALE_REGISTRY[selected_addr]

    # Whale profile card
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#12121a,#1a1a2e);border:1px solid {whale_info["color"]}40;'
        f'border-radius:16px;padding:20px 24px;margin:12px 0 20px 0;">'
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">'
        f'<div style="width:40px;height:40px;border-radius:50%;background:{whale_info["color"]};display:flex;'
        f'align-items:center;justify-content:center;font-weight:900;font-size:1.1rem;color:#0a0a0f;">'
        f'{whale_info["name"][0].upper()}</div>'
        f'<div>'
        f'<div style="font-family:Inter,sans-serif;font-weight:800;font-size:1.2rem;color:#e2e8f0;">'
        f'{whale_info["name"]}</div>'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:0.7rem;color:#64748b;">'
        f'{selected_addr}</div>'
        f'</div></div>'
        f'<div style="display:flex;gap:24px;flex-wrap:wrap;">'
        f'<div><span style="font-family:Inter,sans-serif;font-size:0.7rem;color:#64748b;">ALL-TIME P&L</span><br>'
        f'<span style="font-family:JetBrains Mono,monospace;font-weight:700;font-size:1.1rem;'
        f'color:{"#00ff88" if not whale_info["pnl"].startswith("-") else "#ff3366"};">{whale_info["pnl"]}</span></div>'
        f'<div><span style="font-family:Inter,sans-serif;font-size:0.7rem;color:#64748b;">VOLUME</span><br>'
        f'<span style="font-family:JetBrains Mono,monospace;font-weight:700;font-size:1.1rem;color:#e2e8f0;">'
        f'{whale_info["volume"]}</span></div>'
        f'<div><span style="font-family:Inter,sans-serif;font-size:0.7rem;color:#64748b;">STYLE</span><br>'
        f'<span style="font-family:Inter,sans-serif;font-weight:600;font-size:0.85rem;color:{whale_info["color"]};">'
        f'{whale_info["style"]}</span></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # Two columns: Recent Trades & Open Positions
    whale_col1, whale_col2 = st.columns(2)

    with whale_col1:
        st.markdown(
            '<div style="font-family:Inter,sans-serif;font-weight:800;font-size:1rem;color:#00d4ff;'
            'margin-bottom:12px;">RECENT TRADES</div>',
            unsafe_allow_html=True,
        )

        activities = fetch_whale_activity(selected_addr, limit=25)
        trades_only = [a for a in activities if a.get("type") == "TRADE"]

        if not trades_only:
            st.markdown(
                '<div style="font-family:Inter,sans-serif;font-size:0.85rem;color:#64748b;padding:20px;'
                'text-align:center;">No recent trades found</div>',
                unsafe_allow_html=True,
            )
        else:
            for t in trades_only[:15]:
                title = (t.get("title") or "Unknown")[:55]
                side = t.get("side", "?")
                outcome = t.get("outcome", "?")
                price = float(t.get("price", 0))
                size = float(t.get("size", 0))
                usdc = t.get("usdcSize")
                usdc_str = f"${float(usdc):,.2f}" if usdc else f"${size * price:,.2f}"
                ts = t.get("timestamp", 0)
                if isinstance(ts, str):
                    try:
                        ts = int(ts)
                    except ValueError:
                        ts = 0
                age = int(time.time() - ts) if ts else 0
                if age < 60:
                    age_str = f"{age}s ago"
                elif age < 3600:
                    age_str = f"{age // 60}m ago"
                elif age < 86400:
                    age_str = f"{age // 3600}h ago"
                else:
                    age_str = f"{age // 86400}d ago"

                side_color = "#00ff88" if side == "BUY" else "#ff3366"
                outcome_color = "#00d4ff" if "up" in outcome.lower() or "yes" in outcome.lower() else "#fbbf24"

                st.markdown(
                    f'<div style="background:#12121a;border:1px solid rgba(255,255,255,0.04);border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;font-family:Inter,sans-serif;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="font-size:0.78rem;color:#e2e8f0;font-weight:600;">{title}</span>'
                    f'<span style="font-size:0.65rem;color:#64748b;">{age_str}</span></div>'
                    f'<div style="display:flex;gap:12px;margin-top:6px;font-size:0.72rem;">'
                    f'<span style="color:{side_color};font-weight:700;">{side}</span>'
                    f'<span style="color:{outcome_color};font-weight:600;">{outcome}</span>'
                    f'<span style="color:#94a3b8;">@ {price:.3f}</span>'
                    f'<span style="color:#e2e8f0;font-family:JetBrains Mono,monospace;font-weight:600;">'
                    f'{usdc_str}</span>'
                    f'<span style="color:#64748b;">{size:,.1f} shares</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    with whale_col2:
        st.markdown(
            '<div style="font-family:Inter,sans-serif;font-weight:800;font-size:1rem;color:#a855f7;'
            'margin-bottom:12px;">OPEN POSITIONS</div>',
            unsafe_allow_html=True,
        )

        positions = fetch_whale_positions(selected_addr, limit=20)

        if not positions:
            st.markdown(
                '<div style="font-family:Inter,sans-serif;font-size:0.85rem;color:#64748b;padding:20px;'
                'text-align:center;">No open positions found</div>',
                unsafe_allow_html=True,
            )
        else:
            # Sort by absolute current value descending
            positions.sort(key=lambda p: abs(float(p.get("currentValue", 0))), reverse=True)
            for p in positions[:15]:
                title = (p.get("title") or "Unknown")[:55]
                outcome = p.get("outcome", "?")
                size = float(p.get("size", 0))
                avg_price = float(p.get("avgPrice", 0))
                cur_price = float(p.get("curPrice", 0))
                initial_val = float(p.get("initialValue", 0))
                current_val = float(p.get("currentValue", 0))
                cash_pnl = float(p.get("cashPnl", 0))
                realized_pnl = float(p.get("realizedPnl", 0))

                total_pnl = cash_pnl + realized_pnl
                pnl_color = "#00ff88" if total_pnl >= 0 else "#ff3366"
                pnl_sign = "+" if total_pnl >= 0 else ""

                st.markdown(
                    f'<div style="background:#12121a;border:1px solid rgba(255,255,255,0.04);border-radius:8px;'
                    f'padding:10px 14px;margin-bottom:6px;font-family:Inter,sans-serif;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<span style="font-size:0.78rem;color:#e2e8f0;font-weight:600;">{title}</span>'
                    f'<span style="font-size:0.72rem;color:{pnl_color};font-weight:700;'
                    f'font-family:JetBrains Mono,monospace;">{pnl_sign}${total_pnl:,.2f}</span></div>'
                    f'<div style="display:flex;gap:12px;margin-top:6px;font-size:0.72rem;">'
                    f'<span style="color:#a855f7;font-weight:600;">{outcome}</span>'
                    f'<span style="color:#94a3b8;">{size:,.1f} shares</span>'
                    f'<span style="color:#64748b;">avg {avg_price:.3f}</span>'
                    f'<span style="color:#e2e8f0;">now {cur_price:.3f}</span>'
                    f'<span style="color:#64748b;">val ${current_val:,.2f}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    # All Whales Overview grid
    st.markdown(
        '<div style="font-family:Inter,sans-serif;font-weight:900;font-size:1.1rem;'
        'background:linear-gradient(135deg,#fbbf24,#ff3366);-webkit-background-clip:text;'
        '-webkit-text-fill-color:transparent;background-clip:text;margin:24px 0 12px 0;">'
        'ALL WHALES</div>',
        unsafe_allow_html=True,
    )

    whale_cols = st.columns(3)
    for idx, (addr, info) in enumerate(WHALE_REGISTRY.items()):
        col = whale_cols[idx % 3]
        with col:
            is_selected = "border:2px solid " + info["color"] if addr == selected_addr else "border:1px solid rgba(255,255,255,0.06)"
            pnl_color = "#00ff88" if not info["pnl"].startswith("-") else "#ff3366"
            st.markdown(
                f'<div style="background:linear-gradient(135deg,#12121a,#1a1a2e);{is_selected};'
                f'border-radius:12px;padding:14px 16px;margin-bottom:8px;cursor:pointer;">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
                f'<div style="width:28px;height:28px;border-radius:50%;background:{info["color"]};display:flex;'
                f'align-items:center;justify-content:center;font-weight:900;font-size:0.75rem;color:#0a0a0f;">'
                f'{info["name"][0].upper()}</div>'
                f'<span style="font-family:Inter,sans-serif;font-weight:700;font-size:0.85rem;color:#e2e8f0;">'
                f'{info["name"]}</span></div>'
                f'<div style="display:flex;justify-content:space-between;font-size:0.72rem;">'
                f'<span style="color:{pnl_color};font-family:JetBrains Mono,monospace;font-weight:700;">'
                f'{info["pnl"]}</span>'
                f'<span style="color:#64748b;">{info["volume"]}</span></div>'
                f'<div style="font-size:0.65rem;color:{info["color"]};margin-top:4px;">'
                f'{info["style"]}</div></div>',
                unsafe_allow_html=True,
            )


# =============================================
# TAB 2: SCALPER (3-strategy comparison)
# =============================================
with tab2:
    # --- Coin selector ---
    available_coins = list(COIN_SLUG_PATTERNS.keys())
    coin_col1, coin_col2 = st.columns([1, 4])
    with coin_col1:
        selected_coin = st.selectbox(
            "Coin", [c.upper() for c in available_coins],
            index=0, key="coin_select",
        ).lower()
    coin_label = COIN_LABELS.get(selected_coin, selected_coin.upper())
    coin_color = COIN_COLORS.get(selected_coin, "#f7931a")

    # --- Live price data ---
    coin_data = fetch_crypto_24h(selected_coin)
    live_market = fetch_current_market(selected_coin)

    # Top metrics row
    m1, m2, m3, m4, m5 = st.columns([2, 1, 1, 1, 1])
    with m1:
        if coin_data:
            delta_color = "normal" if coin_data["change_pct"] >= 0 else "inverse"
            st.metric(f"{coin_label}/USDT", f"${coin_data['price']:,.2f}",
                      delta=f"{coin_data['change_pct']:+.2f}%", delta_color=delta_color)
        else:
            st.metric(f"{coin_label}/USDT", "N/A")
    with m2:
        st.metric("24h High", f"${coin_data['high']:,.0f}" if coin_data else "N/A")
    with m3:
        st.metric("24h Low", f"${coin_data['low']:,.0f}" if coin_data else "N/A")
    with m4:
        if live_market:
            st.metric("UP", f"{live_market['up_price']*100:.1f}c")
        else:
            st.metric("UP", "N/A")
    with m5:
        if live_market:
            st.metric("DOWN", f"{live_market['down_price']*100:.1f}c")
        else:
            st.metric("DOWN", "N/A")

    # Market title + gamified countdown timer
    if live_market:
        remaining = live_market["time_remaining"]
        mins, secs = divmod(max(0, int(remaining)), 60)
        total_window = 300  # 5-min window
        pct_remaining = max(0, min(100, (remaining / total_window) * 100))

        if remaining < 60:
            cd_class = "countdown-danger"
            cd_label = "RESOLVING"
            bar_color = "var(--neon-red)"
        elif remaining < 120:
            cd_class = "countdown-warn"
            cd_label = "CLOSING SOON"
            bar_color = "var(--neon-gold)"
        else:
            cd_class = "countdown-safe"
            cd_label = "OPEN"
            bar_color = "var(--neon-green)"

        mkt_title = live_market["title"]
        st.markdown(
            f'<div style="background:var(--bg-card);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:12px 16px;margin:8px 0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<div style="font-family:Inter,sans-serif;font-size:0.75rem;color:#94a3b8;font-weight:500;">{mkt_title}</div>'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="font-family:Inter,sans-serif;font-size:0.6rem;color:{bar_color};text-transform:uppercase;letter-spacing:0.12em;font-weight:700;">{cd_label}</span>'
            f'<span class="countdown {cd_class}">{mins}:{secs:02d}</span>'
            f'</div></div>'
            f'<div style="height:4px;border-radius:2px;background:rgba(255,255,255,0.04);overflow:hidden;">'
            f'<div style="height:100%;width:{pct_remaining:.0f}%;border-radius:2px;background:{bar_color};transition:width 1s linear;"></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    elif selected_coin not in COIN_SLUG_PATTERNS:
        st.warning(f"No Up/Down markets available for {coin_label} yet.")

    # Price chart — neon glow
    klines = fetch_crypto_klines(selected_coin, 30)
    if klines:
        chart_df = pd.DataFrame(klines)
        chart_df["time"] = pd.to_datetime(chart_df["time"], unit="ms")
        r, g, b = int(coin_color[1:3], 16), int(coin_color[3:5], 16), int(coin_color[5:7], 16)
        fig = go.Figure()
        # Glow layer (wider, transparent)
        fig.add_trace(go.Scatter(
            x=chart_df["time"], y=chart_df["close"],
            mode="lines", line=dict(color=f"rgba({r},{g},{b},0.15)", width=12),
            showlegend=False, hoverinfo="skip",
        ))
        # Main line
        fig.add_trace(go.Scatter(
            x=chart_df["time"], y=chart_df["close"],
            mode="lines", line=dict(color=coin_color, width=2.5),
            fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.06)",
            showlegend=False,
        ))
        y_min = chart_df["close"].min() * 0.9999
        y_max = chart_df["close"].max() * 1.0001
        fig.update_layout(
            height=180, margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(showgrid=False, showline=False, zeroline=False, color="#4a5568"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", range=[y_min, y_max], tickformat="$,.0f", color="#4a5568"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            hoverlabel=dict(bgcolor="#1a1a2e", font_color="#e2e8f0", bordercolor="rgba(0,255,136,0.2)"),
        )
        st.plotly_chart(fig, width="stretch")

    st.divider()

    # --- Trading Controls ---
    if st.session_state.get("scalper_running") and not is_scalper_running():
        st.session_state["scalper_running"] = False
    scalper_running = st.session_state.get("scalper_running", False)
    is_live = not cfg.DRY_RUN

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        duration = st.number_input("Duration (min)", value=30, min_value=5, max_value=120, step=5)
    with c2:
        mkt_type = st.selectbox("Window", ["5min", "15min"], index=0)
    with c3:
        if not scalper_running:
            btn_label = "Start LIVE Trading" if is_live else "Start Paper Trading"
            btn_type = "primary"
            if st.button(btn_label, type=btn_type, width="stretch"):
                if is_live:
                    st.session_state["confirm_live"] = True
                    st.rerun()
                else:
                    update_config("SCALP_MARKET_TYPE", mkt_type)
                    start_scalper(duration, mkt_type, selected_coin)
                    st.session_state["scalper_coin"] = selected_coin
                    st.rerun()
        else:
            if st.button("Stop", type="secondary", width="stretch"):
                stop_scalper()
                st.rerun()
    with c4:
        if scalper_running:
            running_coin = st.session_state.get("scalper_coin", "btc").upper()
            if is_live:
                st.markdown(
                    f'<div style="padding:8px 0;">'
                    f'<span class="live-dot red"></span>'
                    f'<span style="font-family:Inter,sans-serif;font-weight:700;color:#ff3366;font-size:0.9rem;">LIVE {running_coin}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="padding:8px 0;">'
                    f'<span class="live-dot green"></span>'
                    f'<span style="font-family:Inter,sans-serif;font-weight:700;color:#00ff88;font-size:0.9rem;">PAPER {running_coin}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            state_check = read_scalper_state()
            if state_check and state_check.get("status") == "finished":
                st.markdown(
                    '<div style="padding:8px 0;font-family:Inter,sans-serif;font-weight:600;color:#94a3b8;">FINISHED</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div style="padding:8px 0;font-family:Inter,sans-serif;font-weight:600;color:#4a5568;">IDLE</div>',
                    unsafe_allow_html=True,
                )

    # --- Live trading confirmation dialog ---
    if st.session_state.get("confirm_live") and not scalper_running:
        st.warning(
            "**WARNING: You are about to trade with REAL MONEY.**\n\n"
            "- The **Current** strategy will place real buy and sell orders on Polymarket\n"
            "- Kelly and Aggressive strategies will remain paper-only\n"
            "- Losses are real and irreversible\n"
            "- Make sure your wallet has USDC funded on Polygon\n\n"
            "**By clicking 'Confirm', you acknowledge that you understand the risks "
            "and that you may lose some or all of your funds.**"
        )
        confirm_cols = st.columns([1, 1, 2])
        with confirm_cols[0]:
            if st.button("Confirm - Start Live", type="primary", width="stretch"):
                update_config("SCALP_MARKET_TYPE", mkt_type)
                start_scalper(duration, mkt_type, selected_coin)
                st.session_state["scalper_coin"] = selected_coin
                st.session_state["confirm_live"] = False
                st.rerun()
        with confirm_cols[1]:
            if st.button("Cancel", width="stretch"):
                st.session_state["confirm_live"] = False
                st.rerun()

    # --- Live mode indicator on running scalper ---
    state = read_scalper_state()
    if state and scalper_running and state.get("dry_run") is False:
        st.error(
            "**LIVE TRADING ACTIVE** -- The Current strategy is placing real orders "
            "with real money. Kelly and Aggressive are paper-only."
        )

    # Read state (may already be read above for live indicator)
    if not state:
        state = read_scalper_state()

    if state and (scalper_running or state.get("status") == "finished"):
        strategies = state.get("strategies", {})

        if strategies:
            # --- 3-Strategy Leaderboard ---
            st.markdown(
                '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">'
                '<span style="font-family:Inter,sans-serif;font-weight:800;font-size:1.2rem;'
                'background:linear-gradient(135deg,#00ff88,#00d4ff);-webkit-background-clip:text;'
                '-webkit-text-fill-color:transparent;background-clip:text;">'
                'STRATEGY ARENA</span></div>',
                unsafe_allow_html=True,
            )

            strat_names = list(strategies.keys())

            # Rank strategies by P&L
            strat_pnl_list = []
            for sn in strat_names:
                sd = strategies[sn]
                sm = sd.get("summary", {})
                bal = sm.get("balance", 100.0)
                starting = sm.get("starting_balance", 100.0)
                pos = sd.get("position")
                disp_bal = bal
                if pos:
                    disp_bal += pos.get("cost", 0) + pos.get("current_pnl", 0)
                strat_pnl_list.append((sn, disp_bal - starting))
            strat_pnl_list.sort(key=lambda x: x[1], reverse=True)
            rank_map = {sn: i + 1 for i, (sn, _) in enumerate(strat_pnl_list)}

            compare_cols = st.columns(len(strat_names))
            card_classes = {"current": "", "kelly": "kelly", "aggressive": "aggressive"}

            for col, sname in zip(compare_cols, strat_names):
                sdata = strategies[sname]
                summary = sdata.get("summary", {})
                display = sdata.get("display_name", sname)
                total_pnl = summary.get("total_pnl", 0)
                balance = summary.get("balance", 100.0)
                starting = summary.get("starting_balance", 100.0)
                has_trades = summary.get("total_trades", 0) > 0
                total_trades = summary.get("total_trades", 0)
                win_rate = summary.get("win_rate", 0)
                roi = summary.get("roi", 0)

                pos_data = sdata.get("position")
                display_balance = balance
                if pos_data:
                    display_balance += pos_data.get("cost", 0) + pos_data.get("current_pnl", 0)
                pnl_from_start = display_balance - starting

                # Calculate streak
                trades = sdata.get("trades", [])
                streak = 0
                streak_type = ""
                for t in reversed(trades):
                    if not streak_type:
                        streak_type = "W" if t.get("pnl", 0) > 0 else "L"
                        streak = 1
                    elif (streak_type == "W" and t.get("pnl", 0) > 0) or (streak_type == "L" and t.get("pnl", 0) <= 0):
                        streak += 1
                    else:
                        break

                rank = rank_map.get(sname, 3)
                card_cls = card_classes.get(sname, "")

                with col:
                    # Rank badge
                    rank_cls = f"rank-{min(rank, 3)}"
                    rank_label = ["", "1ST", "2ND", "3RD"][min(rank, 3)]
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                        f'<span style="font-family:Inter,sans-serif;font-weight:800;font-size:1rem;color:#e2e8f0;">{display}</span>'
                        f'<span class="rank-badge {rank_cls}">{rank_label}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Balance with big P&L
                    pnl_class = "hero-pnl-positive" if pnl_from_start >= 0 else "hero-pnl-negative"
                    st.markdown(
                        f'<div style="text-align:center;margin:12px 0;">'
                        f'<div style="font-family:JetBrains Mono,monospace;font-size:0.75rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;">Balance</div>'
                        f'<span class="{pnl_class}">${display_balance:.2f}</span>'
                        f'<div style="font-family:JetBrains Mono,monospace;font-size:0.85rem;color:{"#00ff88" if pnl_from_start >= 0 else "#ff3366"};">'
                        f'{"+" if pnl_from_start >= 0 else ""}{pnl_from_start:.2f}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Stats row
                    st.metric("Trades", total_trades)

                    # Win rate with progress bar
                    wr_pct = int(win_rate * 100)
                    st.markdown(
                        f'<div style="font-family:Inter,sans-serif;font-size:0.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;">Win Rate</div>'
                        f'<div style="font-family:JetBrains Mono,monospace;font-size:1.1rem;font-weight:700;color:#e2e8f0;">{wr_pct}%</div>'
                        f'<div class="winrate-bar"><div class="winrate-fill" style="width:{wr_pct}%;"></div></div>',
                        unsafe_allow_html=True,
                    )

                    st.metric("ROI", f"{roi:+.1f}%" if has_trades else "-")

                    # Streak
                    if streak > 0:
                        s_cls = "streak-hot" if streak_type == "W" else "streak-cold"
                        s_icon = "W" if streak_type == "W" else "L"
                        st.markdown(
                            f'<div class="streak {s_cls}">{s_icon}{streak}</div>',
                            unsafe_allow_html=True,
                        )

                    # Open position indicator
                    if pos_data:
                        pos_pnl = pos_data.get("current_pnl", 0)
                        badge_cls = "badge-win" if pos_pnl >= 0 else "badge-loss"
                        st.markdown(
                            f'<span class="badge {badge_cls}">{pos_data["side"]} OPEN {pos_pnl:+.2f}</span>',
                            unsafe_allow_html=True,
                        )

                    # Config hints
                    cfg_data = sdata.get("config", {})
                    hints = []
                    if cfg_data.get("use_kelly"):
                        hints.append("Kelly")
                    if cfg_data.get("last_second_only"):
                        hints.append("Last-sec")
                    if cfg_data.get("no_stop_loss"):
                        hints.append("No SL")
                    hints.append(f"{cfg_data.get('min_edge', 0):.0%} edge")
                    st.caption(" | ".join(hints))

            # --- Per-strategy detail tabs ---
            strat_tabs = st.tabs([strategies[s].get("display_name", s) for s in strat_names])

            for stab, sname in zip(strat_tabs, strat_names):
                sdata = strategies[sname]
                with stab:
                    pos = sdata.get("position")
                    if pos:
                        pnl = pos.get("current_pnl", 0)
                        cost = pos.get("cost", 0)
                        current_value = cost + pnl
                        pnl_pct = pos.get("current_pnl_pct", 0)
                        badge_cls = "badge-win" if pnl >= 0 else "badge-loss"
                        pnl_color = "#00ff88" if pnl >= 0 else "#ff3366"
                        st.markdown(
                            f'<div style="background:linear-gradient(135deg,rgba(18,18,26,0.9),rgba(26,26,46,0.7));'
                            f'border:1px solid {"rgba(0,255,136,0.2)" if pnl >= 0 else "rgba(255,51,102,0.2)"};'
                            f'border-radius:12px;padding:16px 24px;margin-bottom:12px;">'
                            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                            f'<div>'
                            f'<span class="badge {badge_cls}">{pos["side"]} POSITION</span>'
                            f'<div style="font-family:JetBrains Mono,monospace;font-size:0.85rem;color:#94a3b8;margin-top:8px;">'
                            f'${cost:.2f} invested</div>'
                            f'</div>'
                            f'<div style="text-align:right;">'
                            f'<div style="font-family:JetBrains Mono,monospace;font-weight:800;font-size:1.4rem;color:{pnl_color};">'
                            f'${current_value:.2f}</div>'
                            f'<div style="font-family:JetBrains Mono,monospace;font-size:0.85rem;color:{pnl_color};">'
                            f'{pnl:+.2f} ({pnl_pct:+.1%})</div>'
                            f'</div></div></div>',
                            unsafe_allow_html=True,
                        )

                    summary = sdata.get("summary", {})
                    if summary.get("total_trades", 0) > 0:
                        tc = summary.get("total_cost", 0)
                        tp = summary.get("total_pnl", 0)
                        tr = tc + tp
                        pnl_color = "#00ff88" if tp >= 0 else "#ff3366"
                        st.markdown(
                            f'<div style="font-family:JetBrains Mono,monospace;font-size:0.9rem;margin:8px 0;">'
                            f'<span style="color:#94a3b8;">${tc:.2f} deployed</span> '
                            f'<span style="color:#4a5568;">&rarr;</span> '
                            f'<span style="color:{pnl_color};font-weight:700;">${tr:.2f}</span> '
                            f'<span style="color:{pnl_color};">({tp:+.2f})</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                    trades = sdata.get("trades", [])
                    if trades:
                        tdf = pd.DataFrame(trades)
                        tdf["result"] = tdf["pnl"].apply(lambda x: "WIN" if x > 0 else "LOSS")
                        if "cost" in tdf.columns:
                            tdf["return"] = tdf["cost"] + tdf["pnl"]
                            tdf["flow"] = tdf.apply(
                                lambda r: f"${r['cost']:.2f} -> ${r['return']:.2f}", axis=1)

                        display_cols = [c for c in ["side", "entry_price", "exit_price", "shares", "flow", "pnl", "result", "exit_type"] if c in tdf.columns]

                        def _color_pnl(val):
                            return f"color: {'#00ff88' if val > 0 else '#ff3366' if val < 0 else '#64748b'}"

                        styled = tdf[display_cols].style.map(_color_pnl, subset=["pnl"])
                        st.dataframe(styled, width="stretch", hide_index=True)
                    else:
                        st.markdown(
                            f'<div style="text-align:center;padding:24px;color:#4a5568;font-family:Inter,sans-serif;">'
                            f'No trades yet &mdash; waiting for signals</div>',
                            unsafe_allow_html=True,
                        )

        # Event log — terminal style
        log_lines = state.get("log", [])
        if log_lines:
            with st.expander("Event Log", expanded=scalper_running):
                log_html = '<div style="background:#0d0d14;border:1px solid rgba(0,255,136,0.1);border-radius:12px;padding:16px;font-family:JetBrains Mono,monospace;font-size:0.75rem;max-height:400px;overflow-y:auto;">'
                for line in log_lines[-30:]:
                    if "WIN" in line or "ENTER" in line or "PROFIT" in line.upper():
                        color = "#00ff88"
                    elif "LOSS" in line or "STOP" in line or "ERROR" in line:
                        color = "#ff3366"
                    elif "Signal" in line or "signal" in line or "edge" in line.lower():
                        color = "#00d4ff"
                    elif "HOLD" in line or "Watching" in line:
                        color = "#a855f7"
                    else:
                        color = "#4a5568"
                    log_html += f'<div style="color:{color};padding:1px 0;">{line}</div>'
                log_html += '</div>'
                st.markdown(log_html, unsafe_allow_html=True)

    elif not scalper_running:
        st.markdown(f"""
**How it works:** Select a coin above, then click **Start Paper Trading**.

The scalper runs 3 strategies simultaneously on the same {coin_label} data:

| Strategy | Edge | Entry | Exit |
|----------|------|-------|------|
| **Current** | 3% min | > 60s left | Profit target / Stop loss |
| **Kelly** | 3% min | > 60s left | Kelly-sized bets |
| **Aggressive** | 1% min | < 60s left | Rides to resolution |

All trades are simulated -- no real money.
        """)

    # --- Trade History (all sessions, always visible) ---
    st.divider()
    with st.expander("Trade History (all sessions)", expanded=False):
        from scalper import load_trade_history
        all_trades = load_trade_history()
        if all_trades:
            hist_df = pd.DataFrame(all_trades)
            for nc in ["cost", "pnl", "pnl_pct", "entry_price", "exit_price", "shares", "edge", "hold_duration_s"]:
                if nc in hist_df.columns:
                    hist_df[nc] = pd.to_numeric(hist_df[nc], errors="coerce")

            hc1, hc2, hc3, hc4 = st.columns(4)
            total_hist_pnl = hist_df["pnl"].sum()
            total_hist_trades = len(hist_df)
            hist_wins = (hist_df["pnl"] > 0).sum()
            hist_wr = hist_wins / total_hist_trades if total_hist_trades else 0
            hc1.metric("Total Trades", total_hist_trades)
            hc2.metric("Total P&L", f"${total_hist_pnl:+.2f}")
            hc3.metric("Win Rate", f"{hist_wr:.0%}")
            hc4.metric("Sessions", hist_df["session_id"].nunique() if "session_id" in hist_df.columns else "?")

            strat_filter = st.selectbox(
                "Filter by strategy", ["All"] + sorted(hist_df["strategy"].dropna().unique().tolist()),
                key="hist_strat_filter",
            )
            if strat_filter != "All":
                hist_df = hist_df[hist_df["strategy"] == strat_filter]

            show_cols = [c for c in [
                "timestamp", "strategy", "coin", "side", "entry_price", "exit_price",
                "cost", "pnl", "pnl_pct", "edge", "exit_type", "hold_duration_s",
            ] if c in hist_df.columns]

            def _color_hist_pnl(val):
                try:
                    v = float(val)
                    return f"color: {'green' if v > 0 else 'red' if v < 0 else 'gray'}"
                except (ValueError, TypeError):
                    return ""

            pnl_cols = [c for c in ["pnl", "pnl_pct"] if c in show_cols]
            styled = hist_df[show_cols].style.map(_color_hist_pnl, subset=pnl_cols)
            st.dataframe(styled, width="stretch", hide_index=True)

            st.download_button(
                "Download Trade Log (CSV)",
                hist_df.to_csv(index=False),
                "scalper_trades_export.csv",
                "text/csv",
            )
        else:
            st.info("No trade history yet. Run the scalper to start collecting data.")

    if scalper_running:
        time.sleep(3)
        st.rerun()


# =============================================
# TAB 6: TRENDING BETS
# =============================================
with tab6:
    st.markdown(
        '<div style="font-family:Inter,sans-serif;font-weight:800;font-size:1.2rem;'
        'background:linear-gradient(135deg,#00ff88,#00d4ff);-webkit-background-clip:text;'
        '-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:12px;">'
        'TRENDING BETS</div>',
        unsafe_allow_html=True,
    )

    @st.cache_data(ttl=60)
    def fetch_trending_markets():
        try:
            resp = requests.get(
                f"{GAMMA_API_URL}/events",
                params={"limit": 20, "active": True, "closed": False, "order": "volume", "ascending": False},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []

    trending = fetch_trending_markets()
    if trending:
        for event in trending[:12]:
            title = event.get("title", "")
            volume = float(event.get("volume", 0) or 0)
            markets = event.get("markets", [])
            if not markets:
                continue
            market = markets[0]
            try:
                prices = json.loads(market.get("outcomePrices", "[]"))
                outcomes = json.loads(market.get("outcomes", "[]"))
            except (json.JSONDecodeError, TypeError):
                continue
            if len(prices) < 2 or len(outcomes) < 2:
                continue

            yes_p = float(prices[0])
            no_p = float(prices[1])
            yes_pct = int(yes_p * 100)

            # Format volume
            if volume >= 1_000_000:
                vol_str = f"${volume/1_000_000:.1f}M"
            elif volume >= 1_000:
                vol_str = f"${volume/1_000:.0f}K"
            else:
                vol_str = f"${volume:.0f}"

            # Card with odds bar
            bar_color = "#00ff88" if yes_pct >= 50 else "#ff3366"
            st.markdown(
                f'<div style="background:linear-gradient(135deg,rgba(18,18,26,0.9),rgba(26,26,46,0.7));'
                f'border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;margin-bottom:8px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
                f'<div style="flex:1;font-family:Inter,sans-serif;font-weight:600;font-size:0.85rem;color:#e2e8f0;">{title}</div>'
                f'<div style="font-family:JetBrains Mono,monospace;font-size:0.75rem;color:#64748b;white-space:nowrap;margin-left:12px;">{vol_str}</div>'
                f'</div>'
                f'<div style="display:flex;gap:12px;margin-top:10px;align-items:center;">'
                f'<span style="font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.9rem;color:#00ff88;">{outcomes[0]} {yes_pct}c</span>'
                f'<div style="flex:1;height:6px;border-radius:3px;background:rgba(255,255,255,0.06);overflow:hidden;">'
                f'<div style="height:100%;width:{yes_pct}%;border-radius:3px;background:{bar_color};"></div>'
                f'</div>'
                f'<span style="font-family:JetBrains Mono,monospace;font-weight:700;font-size:0.9rem;color:#ff3366;">{outcomes[1]} {100-yes_pct}c</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="text-align:center;padding:40px;color:#4a5568;font-family:Inter,sans-serif;">'
            'Could not load trending markets.</div>',
            unsafe_allow_html=True,
        )


# =============================================
# TAB 3: SETTINGS (was Strategy Parameters)
# =============================================
with tab3:
    st.subheader("Settings")
    st.caption("Edit parameters and click Save")

    # Trading Mode
    with st.expander("Trading Mode", expanded=True):
        if cfg.DRY_RUN:
            st.success("**Paper Trading** -- No real money is being used.")
        else:
            st.error(
                "**LIVE TRADING MODE**\n\n"
                "**WARNING: Real money is at stake.** The bot will place actual buy and sell "
                "orders on Polymarket using your connected wallet. You can lose some or all "
                "of your funds. Only the 'Current' strategy trades live -- Kelly and Aggressive "
                "remain paper-only."
            )

        mode_cols = st.columns([1, 2])
        with mode_cols[0]:
            gen_dry_run = st.toggle(
                "Paper Trading Mode" if cfg.DRY_RUN else "Paper Trading Mode (currently OFF)",
                value=cfg.DRY_RUN,
                key="gen_dry",
                help="ON = paper trading (no real money). OFF = live trading (real money)."
            )
        with mode_cols[1]:
            if not gen_dry_run:
                st.markdown(
                    ":red[**You are enabling live trading.**] "
                    "Make sure your wallet has USDC on Polygon."
                )

        if gen_dry_run != cfg.DRY_RUN:
            if st.button("Save Trading Mode", type="primary" if gen_dry_run else "secondary", key="save_mode"):
                update_config("DRY_RUN", gen_dry_run)
                st.success("Saved! Restart the scalper for changes to take effect.")
                st.rerun()

    # General settings
    with st.expander("General Settings", expanded=False):
        gen_cols = st.columns(3)
        with gen_cols[0]:
            gen_bankroll = st.number_input("Total Bankroll ($)", value=cfg.TOTAL_BANKROLL,
                                           min_value=1.0, max_value=10000.0, step=5.0, key="gen_bank")
        with gen_cols[1]:
            gen_kelly = st.slider("Kelly Fraction", 0.10, 1.0, cfg.KELLY_FRACTION, step=0.05, key="gen_kelly")
        with gen_cols[2]:
            pass

        gen_cols2 = st.columns(3)
        with gen_cols2[0]:
            gen_weather_pct = st.slider("Weather Split %", 0, 100, int(cfg.WEATHER_SPLIT * 100), key="gen_wsplit")
        with gen_cols2[1]:
            gen_short_pct = st.slider("Short-Term Split %", 0, 100, int(cfg.SHORT_TERM_SPLIT * 100), key="gen_ssplit")
        with gen_cols2[2]:
            gen_long_pct = max(0, 100 - gen_weather_pct - gen_short_pct)
            st.metric("Longshot Split %", f"{gen_long_pct}%")

        if st.button("Save General", key="save_gen"):
            update_config("TOTAL_BANKROLL", gen_bankroll)
            update_config("KELLY_FRACTION", gen_kelly)
            update_config("WEATHER_SPLIT", gen_weather_pct / 100)
            update_config("SHORT_TERM_SPLIT", gen_short_pct / 100)
            update_config("LONGSHOT_SPLIT", gen_long_pct / 100)
            st.success("Saved!")
            st.rerun()

    # Scalper settings
    with st.expander("Scalper (5-min BTC)"):
        sc_cols = st.columns(3)
        with sc_cols[0]:
            sc_bet = st.number_input("Bet Size ($)", value=cfg.SCALP_BET_SIZE,
                                      min_value=1.0, max_value=100.0, step=1.0, key="sc_bet")
            sc_poll = st.slider("Poll Interval (sec)", 1, 30, cfg.SCALP_POLL_INTERVAL, key="sc_poll")
        with sc_cols[1]:
            sc_edge = st.slider("Min Edge %", 1, 15, int(cfg.SCALP_MIN_EDGE * 100), key="sc_edge")
            sc_profit = st.slider("Profit Target %", 10, 100, int(cfg.SCALP_PROFIT_TARGET * 100), step=5, key="sc_profit")
        with sc_cols[2]:
            sc_stop = st.slider("Stop Loss %", 10, 50, int(cfg.SCALP_STOP_LOSS * 100), step=5, key="sc_stop")
            sc_hedge = st.slider("Hedge Threshold %", 5, 40, int(cfg.SCALP_HEDGE_THRESHOLD * 100), step=5, key="sc_hedge")

        if st.button("Save Scalper", key="save_sc"):
            update_config("SCALP_BET_SIZE", sc_bet)
            update_config("SCALP_POLL_INTERVAL", sc_poll)
            update_config("SCALP_MIN_EDGE", sc_edge / 100)
            update_config("SCALP_PROFIT_TARGET", sc_profit / 100)
            update_config("SCALP_STOP_LOSS", sc_stop / 100)
            update_config("SCALP_HEDGE_THRESHOLD", sc_hedge / 100)
            st.success("Saved!")
            st.rerun()

    # Weather settings
    with st.expander("Weather Grinder"):
        w_cols = st.columns(3)
        with w_cols[0]:
            w_bet = st.number_input("Max Bet ($)", value=cfg.WEATHER_BET_SIZE, step=0.50, key="w_bet")
        with w_cols[1]:
            w_edge = st.slider("Min Edge %", 1, 20, int(cfg.WEATHER_MIN_EDGE * 100), key="w_edge")
        with w_cols[2]:
            w_max = st.number_input("Max Positions", value=cfg.WEATHER_MAX_POSITIONS, min_value=1, max_value=50, key="w_max")

        if st.button("Save Weather", key="save_w"):
            update_config("WEATHER_BET_SIZE", w_bet)
            update_config("WEATHER_MIN_EDGE", w_edge / 100)
            update_config("WEATHER_MAX_POSITIONS", w_max)
            st.success("Saved!")
            st.rerun()

    # Longshot settings
    with st.expander("Long Shot Scanner"):
        l_cols = st.columns(3)
        with l_cols[0]:
            l_bet = st.number_input("Bet Size ($)", value=cfg.LONGSHOT_BET_SIZE, step=0.25, key="l_bet")
            l_auto = st.toggle("Auto-bet Longshots", value=cfg.LONGSHOT_AUTO_BET, key="l_auto")
        with l_cols[1]:
            l_max_price = st.slider("Max Price (cents)", 1, 20, int(cfg.LONGSHOT_MAX_PRICE * 100), key="l_maxp")
            l_max_pos = st.number_input("Max Positions", value=cfg.LONGSHOT_MAX_POSITIONS, min_value=1, max_value=100, key="l_maxpos")
        with l_cols[2]:
            l_min_vol = st.number_input("Min Volume ($)", value=cfg.LONGSHOT_MIN_VOLUME, step=500, key="l_minvol")

        st.caption("Conviction Tiers")
        ct_cols = st.columns(3)
        with ct_cols[0]:
            ct_high = st.number_input("High ($)", value=cfg.CONVICTION_TIERS["high"], step=0.25, key="ct_h")
        with ct_cols[1]:
            ct_med = st.number_input("Medium ($)", value=cfg.CONVICTION_TIERS["medium"], step=0.25, key="ct_m")
        with ct_cols[2]:
            ct_low = st.number_input("Low ($)", value=cfg.CONVICTION_TIERS["low"], step=0.25, key="ct_l")

        if st.button("Save Longshots", key="save_l"):
            update_config("LONGSHOT_BET_SIZE", l_bet)
            update_config("LONGSHOT_AUTO_BET", l_auto)
            update_config("LONGSHOT_MAX_PRICE", l_max_price / 100)
            update_config("LONGSHOT_MAX_POSITIONS", l_max_pos)
            update_config("LONGSHOT_MIN_VOLUME", l_min_vol)
            st.success("Saved!")
            st.rerun()

    # Short-Term Crypto
    with st.expander("Short-Term Crypto"):
        st_cols = st.columns(3)
        with st_cols[0]:
            st_on = st.toggle("Enabled", value=cfg.SHORT_TERM_ENABLED, key="st_on")
            st_bet = st.number_input("Bet Size ($)", value=cfg.SHORT_TERM_BET_SIZE, step=0.25, key="st_bet")
        with st_cols[1]:
            st_edge = st.slider("Min Edge %", 1, 20, int(cfg.SHORT_TERM_MIN_EDGE * 100), key="st_edge")
        with st_cols[2]:
            st_max = st.number_input("Max Positions", value=cfg.SHORT_TERM_MAX_POSITIONS, min_value=1, max_value=20, key="st_max")

        if st.button("Save Short-Term", key="save_st"):
            update_config("SHORT_TERM_ENABLED", st_on)
            update_config("SHORT_TERM_BET_SIZE", st_bet)
            update_config("SHORT_TERM_MIN_EDGE", st_edge / 100)
            update_config("SHORT_TERM_MAX_POSITIONS", st_max)
            st.success("Saved!")
            st.rerun()

    # High-Prob Farming
    with st.expander("High-Prob Farming"):
        hp_cols = st.columns(3)
        with hp_cols[0]:
            hp_on = st.toggle("Enabled", value=cfg.HIGH_PROB_ENABLED, key="hp_on")
            hp_bet = st.number_input("Bet Size ($)", value=cfg.HIGH_PROB_BET_SIZE, step=0.25, key="hp_bet")
        with hp_cols[1]:
            hp_min = st.slider("Min Price (cents)", 80, 99, int(cfg.HIGH_PROB_MIN_PRICE * 100), key="hp_min")
        with hp_cols[2]:
            hp_vol = st.number_input("Min Volume ($)", value=cfg.HIGH_PROB_MIN_VOLUME, step=1000, key="hp_vol")
            hp_max = st.number_input("Max Positions", value=cfg.HIGH_PROB_MAX_POSITIONS, min_value=1, max_value=50, key="hp_max")

        if st.button("Save High-Prob", key="save_hp"):
            update_config("HIGH_PROB_ENABLED", hp_on)
            update_config("HIGH_PROB_BET_SIZE", hp_bet)
            update_config("HIGH_PROB_MIN_PRICE", hp_min / 100)
            update_config("HIGH_PROB_MIN_VOLUME", hp_vol)
            update_config("HIGH_PROB_MAX_POSITIONS", hp_max)
            st.success("Saved!")
            st.rerun()

    # Arbitrage
    with st.expander("Structural Arbitrage"):
        arb_cols = st.columns(3)
        with arb_cols[0]:
            arb_on = st.toggle("Enabled", value=cfg.ARBITRAGE_ENABLED, key="arb_on")
            arb_bet = st.number_input("Bet Size ($)", value=cfg.ARBITRAGE_BET_SIZE, step=0.50, key="arb_bet")
        with arb_cols[1]:
            arb_gap = st.slider("Min Gap %", 1, 10, int(cfg.ARBITRAGE_MIN_GAP * 100), key="arb_gap")
        with arb_cols[2]:
            arb_max = st.number_input("Max Positions", value=cfg.ARBITRAGE_MAX_POSITIONS, min_value=1, max_value=20, key="arb_max")

        if st.button("Save Arbitrage", key="save_arb"):
            update_config("ARBITRAGE_ENABLED", arb_on)
            update_config("ARBITRAGE_BET_SIZE", arb_bet)
            update_config("ARBITRAGE_MIN_GAP", arb_gap / 100)
            update_config("ARBITRAGE_MAX_POSITIONS", arb_max)
            st.success("Saved!")
            st.rerun()


# =============================================
# TAB 4: SIMULATION LAB
# =============================================
with tab4:
    st.subheader("Simulation Lab")

    sim_tab1, sim_tab2 = st.tabs(["Monte Carlo", "Quick Scalper Test"])

    # --- Monte Carlo ---
    with sim_tab1:
        st.markdown("Simulate your current bet portfolio using Monte Carlo to estimate probability of profit, expected ROI, and return distribution.")

        sim_cols = st.columns([1, 1, 2])
        with sim_cols[0]:
            num_sims = st.number_input("Simulations", value=10000, min_value=1000,
                                        max_value=100000, step=1000, key="mc_sims")
        with sim_cols[1]:
            if st.button("Run Monte Carlo", type="primary", key="mc_run"):
                # Load current bets for simulation
                bets_df = load_bets_df()
                open_bets = bets_df[bets_df["status"] == "open"] if not bets_df.empty and "status" in bets_df.columns else pd.DataFrame()

                if open_bets.empty:
                    st.session_state["mc_error"] = "No open bets to simulate. Run a bot scan first."
                else:
                    from simulator import simulate_portfolio
                    sim_bets = []
                    for _, row in open_bets.iterrows():
                        price = row.get("price", 0.50) or 0.50
                        amount = row.get("amount", 1.0) or 1.0
                        prob = row.get("forecast_prob", price) or price
                        sim_bets.append({
                            "bet_amount": amount,
                            "estimated_prob": prob,
                            "payout_if_yes": amount / price if price > 0 else 0,
                        })

                    results = simulate_portfolio(sim_bets, num_simulations=int(num_sims))
                    st.session_state["mc_results"] = results
                    st.session_state.pop("mc_error", None)
                st.rerun()

        # Display error
        if st.session_state.get("mc_error"):
            st.warning(st.session_state["mc_error"])

        # Display results
        mc = st.session_state.get("mc_results")
        if mc:
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Prob of Profit", f"{mc['prob_profit']:.1%}")
            rc2.metric("Expected ROI", f"{mc['expected_roi']:+.1f}%")
            rc3.metric("Median Return", f"${mc['median_return']:+.2f}")
            rc4.metric("Total Risked", f"${mc['total_cost']:.2f}")

            # Percentile table
            pct_cols = st.columns(5)
            pct_cols[0].metric("Worst Case", f"${mc['worst_case']:+.2f}")
            pct_cols[1].metric("5th Pctile", f"${mc['percentile_5']:+.2f}")
            pct_cols[2].metric("25th Pctile", f"${mc['percentile_25']:+.2f}")
            pct_cols[3].metric("75th Pctile", f"${mc['percentile_75']:+.2f}")
            pct_cols[4].metric("Best Case", f"${mc['best_case']:+.2f}")

            # Histogram
            raw = mc.get("results_raw", [])
            if raw:
                fig = go.Figure(go.Histogram(
                    x=raw, nbinsx=40,
                    marker_color="#636efa",
                ))
                fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Break Even")
                fig.update_layout(
                    title=f"Return Distribution ({mc['num_simulations']:,} simulations, {mc['num_bets']} bets)",
                    xaxis_title="P&L ($)", yaxis_title="Frequency",
                    height=400, margin=dict(l=20, r=20, t=40, b=20),
                )
                st.plotly_chart(fig, width="stretch")

    # --- Quick Scalper Test ---
    with sim_tab2:
        st.markdown("Run a quick 5-minute paper trading session from the dashboard.")

        qs_cols = st.columns([1, 1, 2])
        with qs_cols[0]:
            qs_duration = st.number_input("Duration (min)", value=5, min_value=1, max_value=15, key="qs_dur")
        with qs_cols[1]:
            if st.button("Run Quick Test", type="primary", key="qs_run"):
                with st.spinner(f"Running {qs_duration}-minute scalper test..."):
                    runner = os.path.join(BOT_DIR, "scalper_runner.py")
                    try:
                        result = subprocess.run(
                            [sys.executable, runner,
                             "--duration", str(qs_duration),
                             "--state-file", SCALPER_STATE_FILE],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=qs_duration * 60 + 120,
                            cwd=BOT_DIR,
                        )
                        st.session_state["qs_output"] = result.stdout
                    except subprocess.TimeoutExpired:
                        st.session_state["qs_output"] = "Test timed out."
                    except Exception as e:
                        st.session_state["qs_output"] = f"Error: {e}"
                st.rerun()

        if st.session_state.get("qs_output"):
            st.code(st.session_state["qs_output"], language="text")

            # Also show the state file results
            state = read_scalper_state()
            if state and state.get("trades"):
                st.subheader("Results")
                summary = state.get("summary", {})
                r_cols = st.columns(4)
                r_cols[0].metric("Trades", summary.get("total_trades", 0))
                r_cols[1].metric("Win Rate", f"{summary.get('win_rate', 0):.0%}")
                r_cols[2].metric("P&L", f"${summary.get('total_pnl', 0):+.2f}")
                r_cols[3].metric("ROI", f"{summary.get('roi', 0):+.1f}%")


# =============================================
# TAB 5: BET HISTORY
# =============================================
with tab5:
    st.subheader("Bet History")

    if df.empty:
        st.info("No bets logged yet. Click 'Full Scan' in the Overview tab to start.")
    else:
        # Filters
        filter_cols = st.columns(4)
        with filter_cols[0]:
            strat_options = df["strategy"].dropna().unique().tolist()
            strat_filter = st.multiselect("Strategy", strat_options, default=strat_options, key="hist_strat")
        with filter_cols[1]:
            status_options = df["status"].dropna().unique().tolist()
            status_filter = st.multiselect("Status", status_options, default=status_options, key="hist_status")
        with filter_cols[2]:
            cat_options = df["category"].dropna().unique().tolist()
            cat_filter = st.multiselect("Category", cat_options, default=cat_options, key="hist_cat")
        with filter_cols[3]:
            if "timestamp" in df.columns and df["timestamp"].notna().any():
                min_date = df["timestamp"].min().date()
                max_date = df["timestamp"].max().date()
                date_range = st.date_input("Date Range", value=(min_date, max_date),
                                           min_value=min_date, max_value=max_date, key="hist_date")
            else:
                date_range = None

        # Apply filters
        filtered = df[
            (df["strategy"].isin(strat_filter)) &
            (df["status"].isin(status_filter)) &
            (df["category"].isin(cat_filter))
        ]

        if date_range and len(date_range) == 2 and "timestamp" in filtered.columns:
            filtered = filtered[
                (filtered["timestamp"].dt.date >= date_range[0]) &
                (filtered["timestamp"].dt.date <= date_range[1])
            ]

        # Summary row
        sum_cols = st.columns(4)
        sum_cols[0].metric("Total Bets", len(filtered))
        sum_cols[1].metric("Risked", f"${filtered['amount'].sum():.2f}" if not filtered.empty else "$0.00")
        pnl_sum = filtered["pnl"].sum() if not filtered.empty else 0
        sum_cols[2].metric("P&L", f"${pnl_sum:+.2f}")
        risked = filtered['amount'].sum() if not filtered.empty else 0
        sum_cols[3].metric("ROI", f"{(pnl_sum / risked * 100):+.1f}%" if risked > 0 else "N/A")

        # Table
        st.dataframe(
            filtered.sort_values("timestamp", ascending=False),
            width="stretch", height=400, hide_index=True,
        )

        st.download_button(
            "Download CSV",
            filtered.to_csv(index=False),
            "polymarket_bets_export.csv",
            "text/csv",
        )


# =============================================
# TAB: INFO — Strategy explanations & guides
# =============================================
with tab_info:
    st.markdown(
        '<div style="font-family:Inter,sans-serif;font-weight:900;font-size:1.6rem;'
        'background:linear-gradient(135deg,#00d4ff,#a855f7);-webkit-background-clip:text;'
        '-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:8px;">'
        'Strategy Guide</div>'
        '<div style="font-family:Inter,sans-serif;font-size:0.85rem;color:#94a3b8;margin-bottom:24px;">'
        'How each arena strategy works, what edge it exploits, and expected performance.</div>',
        unsafe_allow_html=True,
    )

    strategies_info = [
        {
            "name": "Current",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#128200;",
            "desc": "Standard 3% edge, $5 flat bet, profit target + stop loss exits",
            "details": "The baseline crypto strategy. Calculates edge from Binance price vs Polymarket odds, enters when edge > 3%. Uses fixed $5 bets with 26% profit target and 40% stop loss. This is the 'safe' approach.",
            "expected": "Moderate win rate (~55-65%), steady small gains, low risk per trade.",
        },
        {
            "name": "Kelly",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#128202;",
            "desc": "Kelly criterion bet sizing — mathematically optimal position sizes",
            "details": "Same signal detection as Current, but sizes bets using the Kelly Criterion (f* = (bp - q) / b). Bets more when edge is large, less when edge is small. Theoretically maximizes long-term growth rate.",
            "expected": "Similar win rate to Current, but higher variance. Bigger wins AND bigger losses.",
        },
        {
            "name": "Aggressive",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#128293;",
            "desc": "Last 60s entry, 1% edge threshold, rides to resolution",
            "details": "Enters in the final 60 seconds before the 5-min market resolves. Only needs 1% edge (vs Current's 3%). Never exits early — holds to resolution for full payout. High-conviction, all-or-nothing.",
            "expected": "Lower trade frequency but high conviction. Win = full payout, Loss = total cost.",
        },
        {
            "name": "MicroArb",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#9878;",
            "desc": "Buy YES+NO when gap > 3c — guaranteed profit at resolution",
            "details": "Structural arbitrage. When YES + NO prices sum to < $0.97, buys BOTH sides. At resolution, one side pays $1.00 — profit is locked in regardless of outcome. The 'free money' strategy, if the gap appears.",
            "expected": "Near 100% win rate, but very small profits per trade (1-3%). Depends on gap appearing.",
        },
        {
            "name": "Momentum",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#128640;",
            "desc": "Pure BTC momentum, 0.3% price threshold",
            "details": "Tracks BTC price changes over the last 30 seconds. If price moved > 0.3% in one direction, enters that side immediately. Bets that short-term momentum continues. No edge calculation — pure price action.",
            "expected": "Fast trades, moderate win rate. Works well in trending markets, poorly in choppy ones.",
        },
        {
            "name": "MeanRevert",
            "type": "CRYPTO",
            "type_color": "#00d4ff",
            "icon": "&#128260;",
            "desc": "Contrarian — bet against extreme odds",
            "details": "When UP or DOWN price spikes above 0.70 (70%), bets the opposite direction. Expects the market overreacted and odds will revert toward 50/50. Small bets, high frequency. The 'fade the crowd' play.",
            "expected": "High trade count, moderate win rate. Best when markets are noisy and overreactive.",
        },
        {
            "name": "HighProb",
            "type": "GENERAL",
            "type_color": "#a855f7",
            "icon": "&#127919;",
            "desc": "Buy YES at 92-97c on near-certainties (2-5% ROI)",
            "details": "Scans all Polymarket markets for YES prices between 92-97 cents with volume > $10K. These are events almost certain to happen. Tiny profit per trade but very high win rate. The 'savings account' strategy.",
            "expected": "Very high win rate (90%+), very low ROI per trade (2-5%). Slow but steady.",
        },
        {
            "name": "Longshot",
            "type": "GENERAL",
            "type_color": "#a855f7",
            "icon": "&#127922;",
            "desc": "Sub-5c bets on underpriced markets (20x-100x multiplier)",
            "details": "Finds markets with YES < 5 cents in preferred categories (crypto, economy, weather). Uses category scoring to filter quality. Small $1 bets with potential 20x-100x payout. Exploits favorite-longshot bias.",
            "expected": "Very low win rate (<10%), but one win can pay for 20-100 losses.",
        },
        {
            "name": "Random",
            "type": "BASELINE",
            "type_color": "#64748b",
            "icon": "&#127922;",
            "desc": "Coin flip baseline — the control group",
            "details": "Every hour, picks a random active market and buys YES at whatever price. Fixed $1 bet. No intelligence, no filtering. This is the 'monkey throwing darts' control. Every other strategy SHOULD beat this.",
            "expected": "Should lose money over time (~5-10% loss from fees). If a strategy can't beat Random, it has no real edge.",
        },
    ]

    for s in strategies_info:
        st.markdown(
            f'<div style="background:linear-gradient(135deg,var(--bg-card),var(--bg-card-hover));border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:16px 20px;margin-bottom:8px;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
            f'<span style="font-size:1.3rem;">{s["icon"]}</span>'
            f'<span style="font-family:Inter,sans-serif;font-weight:800;font-size:1rem;color:#e2e8f0;">{s["name"]}</span>'
            f'</div>'
            f'<div style="font-family:Inter,sans-serif;font-size:0.85rem;color:#e2e8f0;font-weight:600;margin-bottom:6px;">{s["desc"]}</div>'
            f'<div style="font-family:Inter,sans-serif;font-size:0.78rem;color:#94a3b8;line-height:1.5;margin-bottom:8px;">{s["details"]}</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:0.7rem;color:#64748b;border-top:1px solid rgba(255,255,255,0.04);padding-top:8px;">Expected: {s["expected"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        '<div style="font-family:Inter,sans-serif;font-weight:700;font-size:0.9rem;color:#94a3b8;margin-bottom:12px;">How the Arena Works</div>'
        '<div style="font-family:Inter,sans-serif;font-size:0.8rem;color:#64748b;line-height:1.7;">'
        '&#8226; Each strategy starts with <b style="color:#e2e8f0;">$100</b> virtual balance<br>'
        '&#8226; 6 strategies trade on 5-min BTC up/down markets (tick every 2-5s)<br>'
        '&#8226; 3 strategies scan broader Polymarket markets for edge (tick every 5 min)<br>'
        '&#8226; All trades include <b style="color:#e2e8f0;">2% slippage</b> and <b style="color:#e2e8f0;">2% fee</b> simulation for realism<br>'
        '&#8226; Minimum order size: 5 shares (Polymarket real minimum)<br>'
        '&#8226; Trades are logged to CSV for future ML training<br>'
        '&#8226; Run overnight, check results in the morning<br>'
        '</div>',
        unsafe_allow_html=True,
    )
