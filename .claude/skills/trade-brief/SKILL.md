---
name: trade-brief
description: >
  Use this skill when the user asks for a full daily briefing, a trade plan
  summary, what to do today, or a combined market + portfolio overview.
  This is the all-in-one morning command. Invoked with /trade-brief.
---

# Trade Brief

Generate a complete morning trade plan: screen → analyze → portfolio status → action list.

This skill orchestrates the full daily loop in one go.

## Steps

1. **Run the full pipeline**
   ```bash
   python3 run_morning.py
   ```
   This runs the screener, analysis, and portfolio show in sequence.

2. **Parse and present a structured briefing**

   After the scripts complete, produce a briefing in this format:

   ---
   ### 📊 Market Snapshot — [DATE]
   *Brief note on overall market direction if known (e.g. SPY trend, any macro events today like Fed meetings, CPI release, major earnings)*

   ### 🏆 Top Candidates
   List the top 5 from the screener with ticker, price, composite score, and which bucket they fall in.

   ### 🎯 Recommended Trades
   Up to 3 specific action items ranked by conviction:
   - **BUY [TICKER]** — [1-line thesis] | Size: $[X] ([N] shares @ $[price]) | Target: +[X]% | Stop: -8%

   ### 💼 Portfolio Status
   - Total value: $[X] ([+/-X]% vs start)
   - Open positions: [N]/8
   - Cash available: $[X]
   - Any alerts: [stop-losses or take-profit flags]

   ### ✅ Action List
   Numbered list of exact steps to take today:
   1. [e.g. Sell AAPL — stop-loss hit at -8.2%]
   2. [e.g. Buy NVDA 943 shares @ $185.50 on Investopedia, then record it]
   3. [e.g. Hold TSLA — earnings in 3 days, sell before close on Thursday]
   ---

3. **Earnings watch**
   Cross-reference current portfolio holdings against the top screener's `earnings_norm` data. If any held stock has earnings within 3 days, remind the user of the strategy: **sell before the report to capture the run-up and avoid the volatility.**

4. **Competition context (optional)**
   If the user asks how they're doing competitively, calculate:
   - Current portfolio return % vs S&P 500 return % since competition start
   - Days remaining in the 3-week window (competition started: ask user if not known)
   - Required daily return to hit a target (e.g. 20% total)

## One-liner for the impatient

If the user just wants the fastest possible start each morning:
```bash
python3 run_morning.py
```
Then invoke `/trade-brief` to get the formatted action plan from the output.
