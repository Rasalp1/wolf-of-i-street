"""
morning_screener.py — Daily stock screener

Pulls data from yfinance + Alpha Vantage for S&P 500 stocks.
Scores each stock on: momentum, volume surge, RSI, upcoming earnings, sentiment.
Outputs a ranked CSV to output/screener_results.csv.
"""

import sys
import time
import datetime as dt

import pandas as pd
import requests
import yfinance as yf

from config import (
    ALPHA_VANTAGE_API_KEY,
    NEWS_API_KEY,
    SCREENER_CSV,
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
        tables = pd.read_html(url)
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
    """Bulk-download price/volume data via yfinance."""
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
    Uses yfinance calendar data.
    """
    print("[INFO] Checking earnings dates ...")
    earnings_proximity = {}
    today = dt.date.today()

    for t in tickers:
        try:
            stock = yf.Ticker(t)
            cal = stock.calendar
            if cal is not None and not cal.empty:
                # calendar can be a DataFrame with columns or a dict
                if isinstance(cal, pd.DataFrame):
                    if "Earnings Date" in cal.columns:
                        ed = pd.to_datetime(cal["Earnings Date"].iloc[0]).date()
                    elif "Earnings Date" in cal.index:
                        ed = pd.to_datetime(cal.loc["Earnings Date"].iloc[0]).date()
                    else:
                        continue
                elif isinstance(cal, dict):
                    if "Earnings Date" in cal:
                        dates = cal["Earnings Date"]
                        ed = dates[0].date() if hasattr(dates[0], "date") else dates[0]
                    else:
                        continue
                else:
                    continue
                days_until = (ed - today).days
                if 0 <= days_until <= 10:
                    earnings_proximity[t] = days_until
        except Exception:
            continue
    return earnings_proximity


def fetch_news_sentiment(tickers: list[str]) -> dict[str, float]:
    """Fetch sentiment signal from NewsAPI (if key provided).
    Returns dict of ticker -> sentiment score (-1 to 1).
    Falls back to Alpha Vantage news sentiment if NewsAPI unavailable.
    """
    sentiment = {}

    if ALPHA_VANTAGE_API_KEY and ALPHA_VANTAGE_API_KEY != "your_alpha_vantage_key_here":
        print("[INFO] Fetching news sentiment from Alpha Vantage ...")
        # Alpha Vantage NEWS_SENTIMENT endpoint — batch up to 50 tickers
        for i in range(0, len(tickers), 50):
            batch = tickers[i : i + 50]
            ticker_str = ",".join(batch)
            url = (
                f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
                f"&tickers={ticker_str}&apikey={ALPHA_VANTAGE_API_KEY}"
            )
            try:
                resp = requests.get(url, timeout=30)
                data = resp.json()
                for item in data.get("feed", []):
                    for ts in item.get("ticker_sentiment", []):
                        tk = ts["ticker"]
                        score = float(ts.get("ticker_sentiment_score", 0))
                        if tk in sentiment:
                            sentiment[tk] = (sentiment[tk] + score) / 2
                        else:
                            sentiment[tk] = score
            except Exception:
                pass
            time.sleep(1)  # rate limit
    elif NEWS_API_KEY and NEWS_API_KEY != "your_newsapi_key_here":
        print("[INFO] Fetching news sentiment from NewsAPI ...")
        # Simple heuristic: count articles per ticker in last 24h
        for t in tickers[:30]:  # limit to avoid rate limits on free tier
            url = (
                f"https://newsapi.org/v2/everything?"
                f"q={t}&from={dt.date.today() - dt.timedelta(days=1)}"
                f"&sortBy=relevancy&pageSize=5&apiKey={NEWS_API_KEY}"
            )
            try:
                resp = requests.get(url, timeout=10)
                data = resp.json()
                count = data.get("totalResults", 0)
                # Normalize: more articles = more buzz, cap at 1.0
                sentiment[t] = min(count / 20, 1.0)
            except Exception:
                pass
            time.sleep(0.5)
    else:
        print("[INFO] No news API key configured — skipping sentiment.")

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

    # Volume surge: cap at 5x and normalize
    df["volume_norm"] = (df["volume_surge"].clip(upper=5) - 1) / 4

    # RSI score: sweet spot is 55-75 (bullish but not overbought)
    # Score peaks at RSI=65, drops off < 40 or > 85
    def rsi_score(rsi):
        if 55 <= rsi <= 75:
            return 1.0
        elif 45 <= rsi < 55:
            return 0.6
        elif 75 < rsi <= 85:
            return 0.5
        elif rsi > 85:
            return 0.1  # overbought
        elif rsi < 30:
            return 0.3  # oversold bounce potential
        else:
            return 0.2

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

    # 2. Earnings calendar
    # Only check earnings for top momentum stocks to save time
    top_momentum = df.nlargest(100, "momentum_score")["ticker"].tolist()
    earnings = fetch_earnings_calendar(top_momentum)
    print(f"[INFO] {len(earnings)} stocks with earnings within 10 days")

    # 3. News sentiment
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
