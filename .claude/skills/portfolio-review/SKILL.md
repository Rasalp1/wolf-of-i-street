---
name: portfolio-review
description: >
  Use this skill when the user asks to check their portfolio, see P&L, record
  a trade, log a buy or sell, check stop-losses, or review current positions.
  Invoked with /portfolio-review.
---

# Portfolio Review

Check live P&L, record trades, and monitor stop-loss alerts.

## Viewing the portfolio

```bash
python3 portfolio_tracker.py show
```

This fetches live prices via yfinance and displays:
- All open positions with current price, market value, P&L, and days held
- Stop-loss alerts (position down ≥ 12% → **SELL IMMEDIATELY**)
- Take-profit flags (position up ≥ 20% → consider trimming)
- Cash remaining and total portfolio value vs starting $1,000,000

## Recording a buy

After executing a trade on Investopedia:
```bash
python3 portfolio_tracker.py buy <TICKER> <SHARES> <PRICE>
```

Example:
```bash
python3 portfolio_tracker.py buy NVDA 943 185.50
```

**Always get the exact fill price from Investopedia** — do not use the screener's last price, as slippage may differ.

## Recording a sell / closing a position

```bash
python3 portfolio_tracker.py sell <TICKER> <PRICE>
```

This closes the entire position. Partial closes are not currently supported — sell the full position and re-enter with the reduced size if needed.

## Stop-loss enforcement (critical)

If `portfolio_tracker.py show` displays a 🚨 STOP-LOSS HIT alert:
1. Tell the user clearly: **"[TICKER] has hit the -12% stop-loss and must be sold now."**
2. Help them calculate the current share count and expected proceeds.
3. Remind them to execute the sell on Investopedia immediately.
4. Record the sell: `python3 portfolio_tracker.py sell TICKER PRICE`
5. **Immediately reinvest the proceeds** — identify the next best screener candidate and recommend a replacement buy to keep cash fully deployed.

**Never suggest holding through a stop-loss.** The -12% rule is hard. But always replace immediately.

## Position sizing guardrails

Before recording any buy, verify:
- Resulting position count ≤ 8
- Position size ≈ $125,000 (adjust slightly for share price rounding)
- Cash after buy ≥ $0

**Goal: $0 idle cash at all times.** If a buy results in small residual cash (< $125k), flag it and recommend filling the remainder with a partial add to the highest-conviction existing position.

## Afternoon review checklist

When the user asks for an afternoon review, run `show` and check:
- [ ] Any stop-losses triggered today?
- [ ] Any positions up >20%? (Consider taking profit and rotating into fresh momentum)
- [ ] Earnings announcements tonight for any held stock? (Sell before close — capture run-up, avoid volatility)
- [ ] Any position held > 5 days with < 3% gain? (Rotate into higher-scoring candidate immediately)
