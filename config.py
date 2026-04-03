"""
Shared configuration and S&P 500 universe for all scripts.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = OUTPUT_DIR / "portfolio.json"
SCREENER_CSV = OUTPUT_DIR / "screener_results.csv"
BRIEFING_FILE = OUTPUT_DIR / "morning_briefing.md"
PRICE_CACHE_FILE = OUTPUT_DIR / "price_cache.pkl"
PRICE_CACHE_TTL_SECONDS = 3600  # 1 hour

# Portfolio settings
TOTAL_CAPITAL = 1_000_000  # Investopedia default
MAX_POSITIONS = 8
POSITION_SIZE = 125_000  # 8 x $125k = $1M fully deployed at all times
STOP_LOSS_PCT = -0.12  # -12% — aggressive strategy, wider stops

# Scoring weights
WEIGHT_MOMENTUM = 0.30
WEIGHT_VOLUME = 0.20
WEIGHT_RSI = 0.20
WEIGHT_EARNINGS = 0.15
WEIGHT_SENTIMENT = 0.15
