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
MAX_POSITIONS = 5
POSITION_SIZE = 200_000  # 5 x $200k = $1M fully deployed, concentrated for max upside
STOP_LOSS_PCT = -0.15  # -15% — wide stops to survive volatile breakout moves

# Scoring weights — heavily favour momentum + volume (the signals behind explosive moves)
WEIGHT_MOMENTUM = 0.35
WEIGHT_VOLUME = 0.30
WEIGHT_RSI = 0.15
WEIGHT_EARNINGS = 0.15
WEIGHT_SENTIMENT = 0.05
