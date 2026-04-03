# 🐺 Wolf of iStreet — Investopedia Simulator Trading System

An AI-powered daily stock screening and analysis system for the Investopedia Stock Simulator competition. Designed to be run entirely through **Claude Code** — you interact via slash commands, Claude handles the scripts.

## One-time setup

```bash
# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Add API keys (Alpha Vantage is free; Anthropic required for analysis)
cp .env.example .env
# Open .env and fill in your keys
```

| Service | Purpose | Free? | Get Key |
|---------|---------|-------|---------|
| Alpha Vantage | News sentiment + technicals | ✅ Free | https://www.alphavantage.co/support/#api-key |
| Anthropic | Claude candidate analysis | Paid | https://console.anthropic.com/ |
| NewsAPI | Fallback sentiment source | ✅ Free tier | https://newsapi.org/ |

The screener works **without any API keys** using yfinance alone. Keys add sentiment scoring and richer analysis.

---

## Daily workflow in Claude Code

Open this project in Claude Code and use the slash commands below. Claude will run the scripts, interpret output, and tell you exactly what to do.

### Every morning (before market open)

```
/trade-brief
```

This is the all-in-one command. It runs the screener, analyzes the top 10 picks with Claude, shows your portfolio status, and produces a formatted action list: what to buy, what to sell, and in what size. **Start here every morning.**

---

### Individual commands

Use these when you want to run a specific step rather than the full pipeline.

#### `/morning-screen`
Scans all S&P 500 stocks and ranks them by composite score. Takes 2–4 minutes. Use this to refresh the candidate list without re-running analysis.

**What it produces:** `output/screener_results.csv` — one row per stock, ranked by composite score.

#### `/analyze-candidates`
Takes the top 10 from the latest screener run and asks Claude to evaluate each one: trade thesis, key risks, entry/exit levels, and recommended position size. Requires `screener_results.csv` to exist.

**What it produces:** `output/morning_briefing.md` — a structured briefing you can read or ask Claude to summarise.

#### `/portfolio-review`
Check your live P&L and record trades after you've executed them on Investopedia.

```
# After buying on Investopedia:
record the buy — tell Claude: "I bought 943 NVDA at 185.50"

# To check current positions and alerts:
/portfolio-review show

# After selling:
record the sell — tell Claude: "I sold NVDA at 200.00"
```

---

## The feedback loop

This system has one manual step: you execute trades on Investopedia yourself, then tell the system what you did. Everything else is automated.

**The only two things you ever report back:**

| Event | Command |
|-------|---------|
| Bought a stock on Investopedia | `python3 portfolio_tracker.py buy TICKER SHARES PRICE` |
| Sold a stock on Investopedia | `python3 portfolio_tracker.py sell TICKER PRICE` |

**What happens when you record a trade:**
- The position is written to `output/portfolio.json` with your fill price, share count, and entry date
- Cash is adjusted accordingly
- Averaging in to an existing position recalculates a blended cost basis automatically

**How it feeds back into analysis:**
Every time `analyze_candidates.py` runs, it reads `portfolio.json` first and passes your current positions as context into each Claude prompt. This means Claude knows what you already hold — it avoids recommending duplicates, flags sector concentration, and sizes new recommendations against your remaining cash.

**What the system never does:**
- It does not place or cancel trades — Investopedia has no API
- It does not read your Investopedia account balance
- Prices in `portfolio.json` are always your reported fill prices, not fetched automatically

The feedback loop in one line: **Investopedia → you → `portfolio_tracker.py` → `portfolio.json` → next morning's analysis.**

---

## Interpreting results

### Screener scores (`screener_results.csv`)

Each stock is scored 0–1 on five signals:

| Signal | Weight | What a high score means |
|--------|--------|------------------------|
| Momentum | 30% | Price well above 20/50-day MA, near 52-week high |
| Volume surge | 20% | Today's volume 2x+ the 30-day average |
| RSI | 20% | RSI between 55–75 (bullish momentum, not overbought) |
| Earnings proximity | 15% | Earnings in 2–5 days — prime for a pre-earnings run-up |
| Sentiment | 15% | Positive news coverage (requires API key) |

**Composite score guide:**
- `> 0.70` — Strong candidate, warrants analysis
- `0.55–0.70` — Watchlist material
- `< 0.55` — Skip unless you have a specific thesis

**Key columns to watch:**
- `earnings_norm = 1.0` → earnings in 2–5 days. This is the highest-edge setup: buy now, sell before the report.
- `volume_surge >= 2.0` → unusual volume often precedes a significant move.
- `rsi` between 55–75 → ideal entry zone. RSI > 85 means overbought — avoid.

### Morning briefing (`morning_briefing.md`)

Each candidate has a strategy bucket:
- **Momentum play** — ride the trend; hold 3–7 days
- **Catalyst trade** — pre-earnings run-up; sell *before* the report
- **Sentiment swing** — news-driven; shorter hold, tighter stop

Conviction levels:
- **High** — sized at ~$175,000 (17.5% of portfolio)
- **Medium** — sized at ~$125,000
- **Low** — skip or paper-watch; don't commit capital

### Portfolio alerts

- 🚨 **STOP-LOSS HIT** — position is down ≥ 8%. Sell immediately on Investopedia, then record it. No exceptions.
- 💰 **TAKE PROFIT** — position is up ≥ 15%. Consider trimming or closing to lock in gains.

---

## Portfolio rules

| Rule | Value |
|------|-------|
| Starting capital | $1,000,000 |
| Max open positions | 8 |
| Target position size | $150,000–200,000 |
| Hard stop-loss | -8% per position |
| Pre-earnings exit | Sell before the earnings report |
| Re-evaluate | Every afternoon — run `/portfolio-review` |

---

## Project structure

```
morning_screener.py      # Screens S&P 500, outputs ranked CSV
analyze_candidates.py    # Claude analysis of top 10 → briefing markdown
portfolio_tracker.py     # CLI: record trades, live P&L, stop-loss alerts
run_morning.py           # Runs all three scripts in sequence
config.py                # Shared constants, scoring weights, paths
.env                     # API keys — never commit this
output/                  # Generated outputs (git-ignored)
.claude/skills/          # Claude Code skill definitions
CLAUDE.md                # Always-loaded project context for Claude
```
