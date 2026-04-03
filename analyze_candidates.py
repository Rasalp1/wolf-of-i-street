"""
analyze_candidates.py — Claude-powered analysis of top screener picks

Takes the top 10 from morning_screener.py output, sends each to Claude
for thesis, risks, entry/exit, and position sizing. Outputs a morning
briefing markdown file.
"""

import datetime as dt
import sys
import json

import pandas as pd

from config import ANTHROPIC_API_KEY, SCREENER_CSV, BRIEFING_FILE, POSITION_SIZE, TOTAL_CAPITAL


def load_top_candidates(n: int = 10) -> pd.DataFrame:
    """Load top N candidates from screener CSV."""
    try:
        df = pd.read_csv(SCREENER_CSV, index_col=0)
    except FileNotFoundError:
        print("[ERROR] Screener results not found. Run morning_screener.py first.")
        sys.exit(1)

    return df.head(n)


def build_analysis_prompt(row: pd.Series, portfolio_context: str) -> str:
    """Build a prompt for Claude to analyze a single stock candidate."""
    return f"""You are an aggressive short-term swing trading analyst for a 3-week stock market simulator competition. 
The portfolio has ${TOTAL_CAPITAL:,} total capital. The goal is to maximize returns — capital preservation is NOT a priority.
We are always fully invested (no idle cash), use $125,000 per position across up to 8 slots, and tolerate a -12% stop-loss.
Bias strongly toward action: if a stock has any compelling signal, recommend buying it.

Analyze this stock candidate and provide a concise trading recommendation:

**{row['ticker']}** — ${row['last_price']}
- Price vs 20-day MA: {row['pct_above_20ma']}%
- Price vs 50-day MA: {row['pct_above_50ma']}%
- % of 52-week high: {row['pct_of_52w_high']}%
- Volume surge (vs 30-day avg): {row['volume_surge']}x
- RSI (14-day): {row['rsi']}
- Earnings proximity score: {row['earnings_norm']} (1.0 = earnings in 2-5 days)
- Sentiment score: {row['sentiment_norm']}
- Composite screener score: {row['composite_score']}

Current portfolio context:
{portfolio_context}

Provide your analysis in this exact format:
**Thesis:** [1-2 sentence bull case]
**Strategy bucket:** [Momentum play / Catalyst trade / Sentiment swing]
**Key risks:** [1-2 biggest risks]
**Entry:** [Buy now / Wait for dip to $X / Skip]
**Target exit:** [$X or +X%]
**Stop-loss:** [$X or -8%]
**Position size:** [$125,000 of ${TOTAL_CAPITAL:,} total — always full slot unless price makes it impractical]
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
        prompt = build_analysis_prompt(row, portfolio_context)
        print(f"  Analyzing {row['ticker']} ...")

        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
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

        target_pct = "+10%" if row["momentum_score"] > 0.5 else "+6%"
        conviction = "High" if row["composite_score"] > 0.7 else "Medium" if row["composite_score"] > 0.5 else "Low"

        analysis = f"""**Thesis:** {row['ticker']} showing strong composite score of {row['composite_score']:.3f} with {row['pct_above_20ma']}% above 20-day MA.
**Strategy bucket:** {bucket}
**Key risks:** Mean reversion if extended; broader market pullback.
**Entry:** Evaluate at market open
**Target exit:** {target_pct}
**Stop-loss:** -8%
**Position size:** ${POSITION_SIZE:,} ({POSITION_SIZE / TOTAL_CAPITAL * 100:.0f}% of portfolio)
**Conviction:** {conviction}
**Time horizon:** 3-7 days"""

        analyses.append({
            "ticker": row["ticker"],
            "price": row["last_price"],
            "composite_score": row["composite_score"],
            "analysis": analysis,
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
