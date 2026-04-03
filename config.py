"""
Shared configuration and S&P 500 universe for all scripts.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

PORTFOLIO_FILE = OUTPUT_DIR / "portfolio.json"
SCREENER_CSV = OUTPUT_DIR / "screener_results.csv"
BRIEFING_FILE = OUTPUT_DIR / "morning_briefing.md"

# Portfolio settings
TOTAL_CAPITAL = 1_000_000  # Investopedia default
MAX_POSITIONS = 8
POSITION_SIZE = 175_000  # ~$150-200k per position
STOP_LOSS_PCT = -0.08  # -8%

# Scoring weights
WEIGHT_MOMENTUM = 0.30
WEIGHT_VOLUME = 0.20
WEIGHT_RSI = 0.20
WEIGHT_EARNINGS = 0.15
WEIGHT_SENTIMENT = 0.15
