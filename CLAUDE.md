# Wolf of iStreet — Claude Project Context

This is an AI-powered daily stock screening system for the **Investopedia Stock Simulator** competition. The goal is to maximise returns over a 3-week period using concentrated positions and AI-assisted screening.

## Project layout

```
morning_screener.py      # Screen S&P 500 stocks, output ranked CSV
analyze_candidates.py    # Claude analysis of top 10 picks → briefing markdown
portfolio_tracker.py     # CLI to track positions, live P&L, stop-loss alerts
run_morning.py           # One-command wrapper that runs all three in sequence
config.py                # All shared constants, paths, scoring weights
.env                     # API keys (never commit this)
output/                  # Generated files — screener_results.csv, morning_briefing.md, portfolio.json
```

## Environment setup

Dependencies are in `requirements.txt`. Install with:
```
pip3 install -r requirements.txt
```

API keys live in `.env` (see `.env.example`). Required keys:
- `ALPHA_VANTAGE_API_KEY` — free at alphavantage.co; used for RSI, technicals, news sentiment
- `ANTHROPIC_API_KEY` — for Claude candidate analysis
- `NEWS_API_KEY` — optional fallback for sentiment (newsapi.org free tier)

The screener runs fine with **no API keys** using yfinance alone. API keys add news sentiment scoring.

## Portfolio rules (always enforce these)

- **Capital:** $1,000,000 (Investopedia default)
- **Max positions:** 8 at any time
- **Position size:** ~$150,000–200,000 per position
- **Stop-loss:** hard cut at **-8%** on any position
- **Re-evaluate:** every afternoon — run portfolio tracker to check alerts
- **Strategy:** concentrated positions, not diversification

## Scoring model

Each S&P 500 stock is scored on five signals weighted as follows:

| Signal | Weight | Logic |
|--------|--------|-------|
| Momentum | 30% | % above 20/50-day MA + proximity to 52-week high |
| Volume surge | 20% | Today's volume vs 30-day average |
| RSI | 20% | Sweet spot 55–75 (bullish, not overbought) |
| Earnings proximity | 15% | 1.0 = earnings in 2–5 days (sweet spot for run-up) |
| News sentiment | 15% | Alpha Vantage or NewsAPI score |

Weights are configurable in `config.py`.

## Three strategy buckets

1. **Momentum plays** — RSI breakouts, high volume, near 52-week highs
2. **Catalyst trades** — buy 2–3 days before earnings/FDA dates, sell before the report
3. **Sentiment swings** — news-driven moves, short-squeeze candidates

## Data sources

| Source | Library / API | What it provides |
|--------|--------------|-----------------|
| Yahoo Finance | `yfinance` (no key) | Prices, volume, earnings calendar |
| Alpha Vantage | REST API + key | Technicals (RSI, MACD), news sentiment |
| S&P 500 universe | Wikipedia (no key) | Ticker list via `pd.read_html` |
| NewsAPI | REST API + key | Headline sentiment (optional) |

## Daily workflow

1. Run `python3 morning_screener.py` → produces `output/screener_results.csv`
2. Run `python3 analyze_candidates.py` → produces `output/morning_briefing.md`
3. Manually execute trades on Investopedia Simulator
4. Record trades: `python3 portfolio_tracker.py buy TICKER SHARES PRICE`
5. Afternoon check: `python3 portfolio_tracker.py show`

Or run everything at once: `python3 run_morning.py`
