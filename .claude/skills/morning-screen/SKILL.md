---
name: morning-screen
description: >
  Use this skill when the user asks to run the morning screen, scan stocks, find
  today's candidates, screen the market, or start the daily workflow. Invoked
  explicitly with /morning-screen.
---

# Morning Screen

Run the daily S&P 500 screener and surface top trading candidates.

## Steps

1. **Check the date and market context**
   - Note today's date and whether US markets are open (Mon–Fri, 9:30am–4pm ET).
   - If the market hasn't opened yet, this is perfect timing — screen before open.

2. **Run the screener**
   ```bash
   cd /path/to/project && python3 morning_screener.py
   ```
   This downloads ~90 days of price/volume data for all S&P 500 stocks via yfinance, computes momentum, volume surge, RSI, earnings proximity, and sentiment scores, then writes a ranked CSV to `output/screener_results.csv`.

3. **Check for errors**
   - If yfinance download fails, confirm internet connectivity.
   - If fewer than 200 stocks return data, there may be a rate-limit issue — wait 60 seconds and retry.
   - Alpha Vantage sentiment is optional; a missing API key is not an error.

4. **Summarise the top results**
   After the run, read `output/screener_results.csv` and present:
   - Top 10 tickers with their composite score, price, RSI, volume surge, and earnings flag
   - Highlight any stocks with `earnings_norm >= 0.5` (earnings within 5 days) — these are catalyst trade candidates
   - Highlight any stocks with `volume_surge >= 2.0` — unusual volume often precedes a move
   - Call out any stocks already in the current portfolio (check `output/portfolio.json`)

5. **Prompt next action**
   Ask whether to proceed to candidate analysis (`/analyze-candidates`) or stop here.

## Tips

- The screener takes 2–4 minutes to run due to bulk yfinance downloads.
- Scores are relative to today's universe — a score of 0.65+ is considered strong.
- Earnings proximity score of 1.0 means earnings are 2–5 days away (sweet spot for run-up trades).
