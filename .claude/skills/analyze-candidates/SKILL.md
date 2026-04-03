---
name: analyze-candidates
description: >
  Use this skill when the user asks to analyze candidates, generate a trade
  briefing, get Claude's opinion on the top picks, or decide what to buy.
  Requires screener_results.csv to exist. Invoked with /analyze-candidates.
---

# Analyze Candidates

Run Claude API analysis on the top 10 screener picks and produce a morning briefing.

## Pre-condition

`output/screener_results.csv` must exist. If it doesn't, run `/morning-screen` first.

## Steps

1. **Check screener freshness**
   - Read the modification timestamp of `output/screener_results.csv`.
   - If it's more than 4 hours old, warn the user and suggest re-running the screener.

2. **Run the analysis script**
   ```bash
   python3 analyze_candidates.py
   ```
   This sends each of the top 10 tickers to Claude (claude-sonnet-4-20250514) with a structured prompt requesting: trade thesis, strategy bucket, key risks, entry/exit levels, position size, conviction, and time horizon.

3. **If `ANTHROPIC_API_KEY` is not set**
   The script falls back to a rule-based template briefing. This is functional but less nuanced. Remind the user to add their key to `.env` for full Claude analysis.

4. **Present the briefing**
   - Read `output/morning_briefing.md` and display it.
   - Group picks by strategy bucket: Momentum plays, Catalyst trades, Sentiment swings.
   - Highlight any High-conviction picks.
   - Flag any picks that conflict with the portfolio rules (already at 8 positions, duplicate sector concentration, etc.).

5. **Position sizing check**
   For any High-conviction pick, confirm the suggested position size respects:
   - Max $200,000 per position
   - Remaining cash in `output/portfolio.json` covers the buy
   - Total positions after buy ≤ 8

6. **Prompt next action**
   Ask which candidates the user wants to trade. Once they decide:
   - Help them calculate exact share counts (dollar amount ÷ current price, round down to whole shares)
   - Remind them to execute the trade on Investopedia first, then record it with `/portfolio-review`

## Example share count calculation

> "I want to put $175,000 into NVDA at $185.50"
> → 175000 ÷ 185.50 = **943 shares** (round down)
