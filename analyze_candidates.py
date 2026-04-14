"""
analyze_candidates.py — Claude-powered analysis of top screener picks

Takes the top 10 from morning_screener.py output, sends each to Claude
for thesis, risks, entry/exit, and position sizing. Outputs a morning
briefing markdown file.
"""

import datetime as dt
import sys
import json
from datetime import date

import pandas as pd

from config import ANTHROPIC_API_KEY, SCREENER_CSV, BRIEFING_FILE, POSITION_SIZE, TOTAL_CAPITAL

OPTIONS_BUDGET = 20_000  # per options play — $20k for massive leverage without blowing the account


def get_options_play(ticker: str, current_price: float, earnings_norm: float) -> dict | None:
    """Fetch the best call option for a candidate from yfinance. Returns a dict or None."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        exps = t.options
        if not exps:
            return None

        today = date.today()

        # For earnings plays (norm >= 0.5) pick the first expiry at least 5 days out.
        # For pure momentum picks at least 10 days out so we have room to run.
        min_days = 5 if earnings_norm >= 0.5 else 10
        target_exp = next(
            (e for e in exps if (date.fromisoformat(e) - today).days >= min_days),
            None,
        )
        if not target_exp:
            return None

        chain = t.option_chain(target_exp)
        calls = chain.calls

        if calls.empty:
            return None

        # Target ATM or up to 5% OTM — sweet spot for leverage vs delta
        atm_calls = calls[
            (calls["strike"] >= current_price) &
            (calls["strike"] <= current_price * 1.05)
        ]
        if atm_calls.empty:
            atm_calls = calls  # fall back to full chain

        idx = (atm_calls["strike"] - current_price).abs().idxmin()
        call = atm_calls.loc[idx]

        # Prefer ask over lastPrice when available (more realistic fill)
        ask = call.get("ask", 0)
        last = call.get("lastPrice", 0)
        premium = ask if ask and ask > 0 else last
        if not premium or premium <= 0:
            return None

        strike = float(call["strike"])
        contracts = max(1, int(OPTIONS_BUDGET / (premium * 100)))
        cost = contracts * premium * 100
        days_out = (date.fromisoformat(target_exp) - today).days

        return {
            "expiry": target_exp,
            "strike": strike,
            "premium": round(premium, 2),
            "breakeven": round(strike + premium, 2),
            "contracts": contracts,
            "cost": round(cost, 2),
            "days_out": days_out,
        }
    except Exception:
        return None


def format_options_play(ticker: str, price: float, opt: dict | None) -> str:
    """Return a markdown snippet for the options play section."""
    if opt is None:
        return "_Options data unavailable for this ticker._"

    pct_to_breakeven = round((opt["breakeven"] - price) / price * 100, 1)
    return (
        f"**Call Option:** ${opt['strike']} strike · Expires {opt['expiry']} ({opt['days_out']}d)\n"
        f"**Premium:** ~${opt['premium']}/contract · {opt['contracts']} contracts = ~${opt['cost']:,.0f}\n"
        f"**Break-even at expiry:** ${opt['breakeven']} (+{pct_to_breakeven}% from here)\n"
        f"**Upside:** If {ticker} moves +15%, this call could return 100–300%"
    )


def load_top_candidates(n: int = 10) -> pd.DataFrame:
    """Load top N candidates from screener CSV."""
    try:
        df = pd.read_csv(SCREENER_CSV, index_col=0)
    except FileNotFoundError:
        print("[ERROR] Screener results not found. Run morning_screener.py first.")
        sys.exit(1)

    return df.head(n)


def build_analysis_prompt(row: pd.Series, portfolio_context: str, opt: dict | None) -> str:
    """Build a prompt for Claude to analyze a single stock candidate."""
    options_context = (
        f"Live options data: ${opt['strike']} call expiring {opt['expiry']} ({opt['days_out']}d), "
        f"premium ~${opt['premium']}, break-even ${opt['breakeven']}. "
        f"${OPTIONS_BUDGET:,} budget = {opt['contracts']} contracts."
        if opt else "Options data unavailable for this ticker."
    )

    return f"""You are a high-conviction short-term trader running a stock simulator competition with a 2-week window.
This is NOT real money — the ONLY goal is maximum return percentage. Capital preservation is irrelevant.
Portfolio: ${TOTAL_CAPITAL:,} total, 5 concentrated positions at $200,000 each, -15% stop-loss.
Think like a hedge fund running a 2-week sprint: swing for the fences, pick the stocks most likely to make explosive moves.
High RSI, extended charts, and overbought conditions are fine — momentum is the edge here.
The simulator supports options trading. Recommend an options play where conviction is high.

Analyze this candidate:

**{row['ticker']}** — ${row['last_price']}
- Price vs 20-day MA: {row['pct_above_20ma']}%
- Price vs 50-day MA: {row['pct_above_50ma']}%
- % of 52-week high: {row['pct_of_52w_high']}%
- Volume surge (vs 30-day avg): {row['volume_surge']}x
- RSI (14-day): {row['rsi']}
- Earnings proximity score: {row['earnings_norm']} (1.0 = earnings in 2-5 days)
- Sentiment score: {row['sentiment_norm']}
- Composite screener score: {row['composite_score']}

{options_context}

Current portfolio context:
{portfolio_context}

Provide your analysis in this exact format:
**Thesis:** [1-2 sentence bull case — why will this make a big move in the next 1-10 days?]
**Strategy bucket:** [Momentum play / Catalyst trade / Sentiment swing]
**Key risks:** [1 biggest risk]
**Entry:** [Buy now / Wait for dip to $X / Skip]
**Target exit:** [$X or +X% — aim for +15-25% on big setups]
**Stop-loss:** [-15%]
**Position size:** [$200,000 of ${TOTAL_CAPITAL:,} total]
**Options play:** [If conviction High: describe the call option — strike, expiry, contracts, why it amplifies this trade. If conviction Medium/Low: Skip options.]
**Conviction:** [High / Medium / Low]
**Time horizon:** [X days]"""


def analyze_with_claude(candidates: pd.DataFrame, portfolio_context: str) -> list[dict]:
    """Send each candidate to Claude for analysis."""
    try:
        import anthropic
    except ImportError:
        print("[ERROR] anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
        print("[WARN] No Anthropic API key — generating template briefing instead.")
        return generate_template_briefing(candidates)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    analyses = []

    for _, row in candidates.iterrows():
        print(f"  Analyzing {row['ticker']} ...")
        opt = get_options_play(row["ticker"], row["last_price"], row["earnings_norm"])
        prompt = build_analysis_prompt(row, portfolio_context, opt)

        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            analysis_text = message.content[0].text
        except Exception as e:
            analysis_text = f"[Analysis failed: {e}]"

        analyses.append({
            "ticker": row["ticker"],
            "price": row["last_price"],
            "composite_score": row["composite_score"],
            "analysis": analysis_text,
            "options": opt,
        })

    return analyses


def generate_template_briefing(candidates: pd.DataFrame) -> list[dict]:
    """Generate a template briefing when no API key is available."""
    analyses = []
    for _, row in candidates.iterrows():
        # Determine strategy bucket based on scores
        if row["earnings_norm"] >= 0.5:
            bucket = "Catalyst trade (upcoming earnings)"
        elif row["volume_surge"] >= 2.0:
            bucket = "Momentum play (volume breakout)"
        elif row["sentiment_norm"] >= 0.7:
            bucket = "Sentiment swing"
        else:
            bucket = "Momentum play"

        target_pct = "+20%" if row["composite_score"] > 0.7 else "+15%"
        conviction = "High" if row["composite_score"] > 0.7 else "Medium" if row["composite_score"] > 0.5 else "Low"

        opt = get_options_play(row["ticker"], row["last_price"], row["earnings_norm"])
        options_line = format_options_play(row["ticker"], row["last_price"], opt)

        analysis = f"""**Thesis:** {row['ticker']} showing composite score of {row['composite_score']:.3f} with {row['pct_above_20ma']}% above 20-day MA and {row['volume_surge']}x volume surge — momentum candidate for explosive near-term move.
**Strategy bucket:** {bucket}
**Key risks:** Broad market reversal.
**Entry:** Buy at market open
**Target exit:** {target_pct}
**Stop-loss:** -15%
**Position size:** ${POSITION_SIZE:,} ({POSITION_SIZE / TOTAL_CAPITAL * 100:.0f}% of portfolio)
**Conviction:** {conviction}
**Time horizon:** 3-7 days

#### Options Play
{options_line}"""

        analyses.append({
            "ticker": row["ticker"],
            "price": row["last_price"],
            "composite_score": row["composite_score"],
            "analysis": analysis,
            "options": opt,
        })

    return analyses


def write_briefing(analyses: list[dict]):
    """Write the morning briefing to a markdown file."""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# 🐺 Wolf of iStreet — Morning Briefing",
        f"**Generated:** {now}\n",
        "---\n",
    ]

    for i, a in enumerate(analyses, 1):
        lines.append(f"## #{i} — {a['ticker']} (${a['price']}) | Score: {a['composite_score']:.3f}\n")
        lines.append(a["analysis"])
        lines.append("\n---\n")

    # Summary table
    lines.append("## Quick Reference\n")
    lines.append("| Rank | Ticker | Price | Score |")
    lines.append("|------|--------|-------|-------|")
    for i, a in enumerate(analyses, 1):
        lines.append(f"| {i} | {a['ticker']} | ${a['price']} | {a['composite_score']:.3f} |")

    # Options summary table
    options_rows = [(i, a) for i, a in enumerate(analyses, 1) if a.get("options")]
    if options_rows:
        lines.append("\n## Options Plays Summary\n")
        lines.append("| Rank | Ticker | Strike | Expiry | Premium | Break-even | Contracts | Cost |")
        lines.append("|------|--------|--------|--------|---------|------------|-----------|------|")
        for i, a in options_rows:
            opt = a["options"]
            lines.append(
                f"| {i} | {a['ticker']} | ${opt['strike']} | {opt['expiry']} "
                f"| ${opt['premium']} | ${opt['breakeven']} "
                f"| {opt['contracts']} | ${opt['cost']:,.0f} |"
            )

    content = "\n".join(lines)
    BRIEFING_FILE.write_text(content)
    print(f"\n[OK] Morning briefing saved to {BRIEFING_FILE}")
    print(f"\n{'=' * 60}")
    print(content)


def main():
    print("=" * 60)
    print("  WOLF OF iSTREET — Claude Analysis")
    print(f"  {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Load portfolio context if available
    from config import PORTFOLIO_FILE
    portfolio_context = "No current positions (starting fresh)."
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE) as f:
                pf = json.load(f)
            positions = pf.get("positions", [])
            if positions:
                pos_strs = [f"  {p['ticker']}: {p['shares']} shares @ ${p['avg_cost']}" for p in positions]
                portfolio_context = "Current positions:\n" + "\n".join(pos_strs)
        except Exception:
            pass

    candidates = load_top_candidates(10)
    print(f"[INFO] Analyzing top {len(candidates)} candidates ...\n")

    analyses = analyze_with_claude(candidates, portfolio_context)
    write_briefing(analyses)


if __name__ == "__main__":
    main()
