"""
morning_screener.py — Daily stock screener

Pulls data from yfinance + Finnhub for S&P 500 stocks.
Scores each stock on: momentum, volume surge, RSI, upcoming earnings, sentiment.
Outputs a ranked CSV to output/screener_results.csv.
"""

import sys
import time
import datetime as dt
import pickle
from io import StringIO

import urllib3
import pandas as pd
import requests
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    FINNHUB_API_KEY,
    SCREENER_CSV,
    PRICE_CACHE_FILE,
    PRICE_CACHE_TTL_SECONDS,
    WEIGHT_MOMENTUM,
    WEIGHT_VOLUME,
    WEIGHT_RSI,
    WEIGHT_EARNINGS,
    WEIGHT_SENTIMENT,
)


# ---------------------------------------------------------------------------
# S&P 500 universe
# ---------------------------------------------------------------------------

def get_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 tickers from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; WolfOfIStreet/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        return tickers
    except Exception as e:
        print(f"[WARN] Could not fetch S&P 500 list: {e}")
        # Fallback: a small curated high-liquidity list
        return [
            "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "JPM",
            "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "HD", "CVX", "MRK",
            "ABBV", "LLY", "PEP", "KO", "COST", "AVGO", "TMO", "MCD", "CSCO",
            "ACN", "ABT", "DHR", "WFC", "NEE", "LIN", "TXN", "PM", "UPS",
            "AMD", "RTX", "LOW", "SCHW", "COP", "BA", "AMGN", "SPGI", "GS",
            "CAT", "BLK", "ISRG", "ELV", "INTC", "SBUX", "MDLZ", "ADI",
        ]


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def fetch_yfinance_data(tickers: list[str]) -> pd.DataFrame:
    """Bulk-download price/volume data via yfinance, with 1-hour local cache."""
    # Check for a fresh cache
    if PRICE_CACHE_FILE.exists():
        age = dt.datetime.now().timestamp() - PRICE_CACHE_FILE.stat().st_mtime
        if age < PRICE_CACHE_TTL_SECONDS:
            print(f"[INFO] Using cached price data ({int(age / 60)}m old) — skipping download.")
            with open(PRICE_CACHE_FILE, "rb") as f:
                return pickle.load(f)

    print(f"[INFO] Downloading price data for {len(tickers)} tickers ...")
    end = dt.date.today()
    start = end - dt.timedelta(days=90)  # ~3 months for MA calcs

    data = yf.download(
        tickers,
        start=start.isoformat(),
        end=end.isoformat(),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
    )

    # Persist to cache
    with open(PRICE_CACHE_FILE, "wb") as f:
        pickle.dump(data, f)
    print(f"[INFO] Price data cached to {PRICE_CACHE_FILE}")

    return data


def compute_momentum_and_volume(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Compute momentum score and volume surge for each ticker."""
    rows = []
    for t in tickers:
        try:
            if len(tickers) == 1:
                df = data
            else:
                df = data[t]
            if df.empty or df["Close"].dropna().shape[0] < 50:
                continue
            close = df["Close"].dropna()
            volume = df["Volume"].dropna()

            last_price = float(close.iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            high_52w = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())

            # Momentum: % above 20-day and 50-day MA, proximity to 52-wk high
            pct_above_20 = (last_price - ma20) / ma20
            pct_above_50 = (last_price - ma50) / ma50
            pct_of_high = last_price / high_52w

            momentum_score = (pct_above_20 * 0.4 + pct_above_50 * 0.3 + pct_of_high * 0.3)

            # Volume: today vs 30-day average
            vol_today = float(volume.iloc[-1])
            vol_30d = float(volume.tail(30).mean())
            volume_surge = vol_today / vol_30d if vol_30d > 0 else 1.0

            # RSI (14-day)
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
            rsi = 100 - (100 / (1 + rs))

            rows.append({
                "ticker": t,
                "last_price": round(last_price, 2),
                "ma20": round(ma20, 2),
                "ma50": round(ma50, 2),
                "pct_above_20ma": round(pct_above_20 * 100, 2),
                "pct_above_50ma": round(pct_above_50 * 100, 2),
                "pct_of_52w_high": round(pct_of_high * 100, 2),
                "momentum_score": round(momentum_score, 4),
                "volume_surge": round(volume_surge, 2),
                "rsi": round(float(rsi), 2),
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def fetch_earnings_calendar(tickers: list[str]) -> dict[str, int]:
    """Return dict of ticker -> days until next earnings (if within 10 days).
    Uses Finnhub /calendar/earnings — single API call for the full date range.
    """
    if not FINNHUB_API_KEY:
        print("[INFO] No Finnhub API key — skipping earnings calendar.")
        return {}

    print("[INFO] Fetching earnings calendar from Finnhub ...")
    today = dt.date.today()
    to_date = today + dt.timedelta(days=10)
    url = (
        f"https://finnhub.io/api/v1/calendar/earnings"
        f"?from={today}&to={to_date}&token={FINNHUB_API_KEY}"
    )
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        ticker_set = set(tickers)
        earnings_proximity = {}
        for event in data.get("earningsCalendar", []):
            symbol = event.get("symbol", "")
            date_str = event.get("date", "")
            if symbol in ticker_set and date_str:
                ed = dt.date.fromisoformat(date_str)
                days_until = (ed - today).days
                if 0 <= days_until <= 10:
                    earnings_proximity[symbol] = days_until
        return earnings_proximity
    except Exception as e:
        print(f"[WARN] Finnhub earnings calendar failed: {e}")
        return {}


# Keyword sets for headline sentiment scoring
_BULLISH = {
    "beats", "beat", "surges", "surge", "jumps", "jump", "rises", "rise",
    "rallies", "rally", "upgrade", "upgraded", "outperform", "record",
    "growth", "profit", "raises", "raised", "positive", "bullish", "gains",
    "gain", "breakout", "soars", "soar", "strong", "expands", "expansion",
}
_BEARISH = {
    "misses", "miss", "falls", "fall", "drops", "drop", "slips", "slip",
    "downgrade", "downgraded", "underperform", "loss", "cuts", "cut",
    "negative", "bearish", "declines", "decline", "warning", "lawsuit",
    "investigation", "recall", "layoffs", "layoff", "weak", "disappoints",
}


def _score_headline(text: str) -> float:
    """Score a news snippet -1.0 (bearish) to +1.0 (bullish) via keywords."""
    words = set(text.lower().split())
    bull = len(words & _BULLISH)
    bear = len(words & _BEARISH)
    if bull + bear == 0:
        return 0.0
    return (bull - bear) / (bull + bear)


def fetch_news_sentiment(tickers: list[str]) -> dict[str, float]:
    """Fetch company news via Finnhub and score headlines with keyword analysis.
    Returns dict of ticker -> sentiment score (-1 to 1).
    Free tier: 60 req/min — sleeps 1 s between calls.
    """
    if not FINNHUB_API_KEY:
        print("[INFO] No Finnhub API key — skipping news sentiment.")
        return {}

    batch = tickers[:50]
    print(f"[INFO] Fetching news sentiment from Finnhub for {len(batch)} tickers ...")
    sentiment = {}
    today = dt.date.today()
    from_date = (today - dt.timedelta(days=3)).isoformat()
    to_date = today.isoformat()

    for i, t in enumerate(batch):
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={t}&from={from_date}&to={to_date}&token={FINNHUB_API_KEY}"
        )
        try:
            resp = requests.get(url, timeout=10)
            articles = resp.json()
            if isinstance(articles, list) and articles:
                scores = [
                    _score_headline(a.get("headline", "") + " " + a.get("summary", ""))
                    for a in articles[:10]
                ]
                sentiment[t] = sum(scores) / len(scores)
        except Exception as e:
            print(f"[WARN] Finnhub news failed for {t}: {e}")
        if i < len(batch) - 1:
            time.sleep(1.1)  # stay within 60 req/min free tier

    return sentiment


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def score_stocks(df: pd.DataFrame, earnings: dict, sentiment: dict) -> pd.DataFrame:
    """Combine all signals into a single composite score."""

    # Normalize momentum_score to 0-1 range
    m_min, m_max = df["momentum_score"].min(), df["momentum_score"].max()
    if m_max > m_min:
        df["momentum_norm"] = (df["momentum_score"] - m_min) / (m_max - m_min)
    else:
        df["momentum_norm"] = 0.5

    # Volume surge: cap at 10x — reward massive spikes that signal institutional activity
    df["volume_norm"] = (df["volume_surge"].clip(upper=10) - 1) / 9

    # RSI score: favour breakout momentum (65-85 is the power zone for aggressive plays)
    # High RSI is a FEATURE not a bug — it means the stock is running
    def rsi_score(rsi):
        if 65 <= rsi <= 85:
            return 1.0   # breakout power zone
        elif 55 <= rsi < 65:
            return 0.75  # building momentum
        elif 85 < rsi <= 95:
            return 0.6   # extended but still running
        elif 45 <= rsi < 55:
            return 0.35
        elif rsi > 95:
            return 0.2   # blow-off top risk
        elif rsi < 30:
            return 0.3   # oversold bounce potential
        else:
            return 0.1

    df["rsi_norm"] = df["rsi"].apply(rsi_score)

    # Earnings proximity: stocks with earnings in 2-5 days get highest score
    def earnings_score(ticker):
        days = earnings.get(ticker, 99)
        if 2 <= days <= 5:
            return 1.0  # sweet spot: capture run-up before report
        elif days <= 1:
            return 0.3  # too close, high risk
        elif 6 <= days <= 10:
            return 0.5
        return 0.0

    df["earnings_norm"] = df["ticker"].apply(earnings_score)

    # Sentiment
    def sentiment_score(ticker):
        s = sentiment.get(ticker, 0)
        return max(0, min(1, (s + 1) / 2))  # map -1..1 to 0..1

    df["sentiment_norm"] = df["ticker"].apply(sentiment_score)

    # Composite
    df["composite_score"] = (
        WEIGHT_MOMENTUM * df["momentum_norm"]
        + WEIGHT_VOLUME * df["volume_norm"]
        + WEIGHT_RSI * df["rsi_norm"]
        + WEIGHT_EARNINGS * df["earnings_norm"]
        + WEIGHT_SENTIMENT * df["sentiment_norm"]
    )

    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df.index += 1  # 1-based rank
    df.index.name = "rank"

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  WOLF OF iSTREET — Morning Screener")
    print(f"  {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    tickers = get_sp500_tickers()
    print(f"[INFO] Universe: {len(tickers)} tickers")

    # 1. Price + volume + RSI from yfinance
    raw_data = fetch_yfinance_data(tickers)
    df = compute_momentum_and_volume(raw_data, tickers)
    print(f"[INFO] Got data for {len(df)} tickers")

    if df.empty:
        print("[ERROR] No data — check your internet connection.")
        sys.exit(1)

    # 2. Earnings calendar — Finnhub returns all in one API call
    earnings = fetch_earnings_calendar(tickers)
    print(f"[INFO] {len(earnings)} stocks with earnings within 10 days")

    # 3. News sentiment — per-ticker Finnhub calls, limited to top momentum
    top_momentum = df.nlargest(50, "momentum_score")["ticker"].tolist()
    sentiment = fetch_news_sentiment(top_momentum)
    print(f"[INFO] Got sentiment for {len(sentiment)} tickers")

    # 4. Score and rank
    df = score_stocks(df, earnings, sentiment)

    # 5. Output
    df.to_csv(SCREENER_CSV)
    print(f"\n[OK] Results saved to {SCREENER_CSV}")

    # Print top 20
    print("\n" + "=" * 60)
    print("  TOP 20 CANDIDATES")
    print("=" * 60)
    cols = ["ticker", "last_price", "pct_above_20ma", "volume_surge", "rsi",
            "earnings_norm", "sentiment_norm", "composite_score"]
    print(df.head(20)[cols].to_string())

    return df


if __name__ == "__main__":
    main()
