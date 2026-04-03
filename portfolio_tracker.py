"""
portfolio_tracker.py — Track positions, P&L, stop-loss alerts

Tracks your Investopedia Simulator positions locally.
Fetches live prices, calculates P&L, flags stop-losses, suggests trims.
Stores state in output/portfolio.json.
"""

import datetime as dt
import json
import sys

import pandas as pd
import yfinance as yf

from config import PORTFOLIO_FILE, TOTAL_CAPITAL, STOP_LOSS_PCT, MAX_POSITIONS, POSITION_SIZE


# ---------------------------------------------------------------------------
# Portfolio data model
# ---------------------------------------------------------------------------

def load_portfolio() -> dict:
    """Load portfolio from JSON file."""
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {
        "created": dt.datetime.now().isoformat(),
        "starting_capital": TOTAL_CAPITAL,
        "cash": TOTAL_CAPITAL,
        "positions": [],
        "closed_trades": [],
    }


def save_portfolio(pf: dict):
    """Save portfolio to JSON file."""
    pf["last_updated"] = dt.datetime.now().isoformat()
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(pf, f, indent=2, default=str)
    print(f"[OK] Portfolio saved to {PORTFOLIO_FILE}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def add_position(pf: dict, ticker: str, shares: int, price: float) -> dict:
    """Record a new position (manually entered after Investopedia trade)."""
    cost = shares * price
    if cost > pf["cash"]:
        print(f"[ERROR] Not enough cash. Have ${pf['cash']:,.2f}, need ${cost:,.2f}")
        return pf

    existing = [p for p in pf["positions"] if p["ticker"] == ticker]
    if existing:
        # Average into existing position
        pos = existing[0]
        total_shares = pos["shares"] + shares
        pos["avg_cost"] = (pos["avg_cost"] * pos["shares"] + price * shares) / total_shares
        pos["shares"] = total_shares
        pos["total_cost"] = pos["avg_cost"] * total_shares
        print(f"[OK] Averaged into {ticker}: now {total_shares} shares @ ${pos['avg_cost']:.2f}")
    else:
        if len(pf["positions"]) >= MAX_POSITIONS:
            print(f"[WARN] Already at max {MAX_POSITIONS} positions. Close one first.")
            return pf
        pf["positions"].append({
            "ticker": ticker,
            "shares": shares,
            "avg_cost": price,
            "total_cost": cost,
            "entry_date": dt.date.today().isoformat(),
        })
        print(f"[OK] Added {shares} shares of {ticker} @ ${price:.2f} (${cost:,.2f})")

    pf["cash"] -= cost
    return pf


def close_position(pf: dict, ticker: str, price: float) -> dict:
    """Close a position (record after selling on Investopedia)."""
    pos = [p for p in pf["positions"] if p["ticker"] == ticker]
    if not pos:
        print(f"[ERROR] No position in {ticker}")
        return pf

    pos = pos[0]
    proceeds = pos["shares"] * price
    pnl = proceeds - pos["total_cost"]
    pnl_pct = pnl / pos["total_cost"] * 100

    pf["closed_trades"].append({
        "ticker": ticker,
        "shares": pos["shares"],
        "avg_cost": pos["avg_cost"],
        "exit_price": price,
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "entry_date": pos["entry_date"],
        "exit_date": dt.date.today().isoformat(),
    })

    pf["positions"] = [p for p in pf["positions"] if p["ticker"] != ticker]
    pf["cash"] += proceeds

    sign = "+" if pnl >= 0 else ""
    print(f"[OK] Closed {ticker}: {sign}${pnl:,.2f} ({sign}{pnl_pct:.1f}%)")
    return pf


# ---------------------------------------------------------------------------
# Live P&L + alerts
# ---------------------------------------------------------------------------

def show_portfolio(pf: dict):
    """Display current portfolio with live prices and P&L."""
    print("\n" + "=" * 70)
    print("  WOLF OF iSTREET — Portfolio Tracker")
    print(f"  {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    if not pf["positions"]:
        print("\n  No open positions.")
        print(f"  Cash: ${pf['cash']:,.2f}")
        print_closed_trades(pf)
        return

    tickers = [p["ticker"] for p in pf["positions"]]
    print(f"\n[INFO] Fetching live prices for {len(tickers)} positions ...")

    # Fetch current prices
    prices = {}
    for t in tickers:
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="1d")
            if not hist.empty:
                prices[t] = float(hist["Close"].iloc[-1])
        except Exception:
            pass

    # Display
    total_value = pf["cash"]
    total_cost = 0

    rows = []
    alerts = []

    for pos in pf["positions"]:
        t = pos["ticker"]
        current = prices.get(t)
        if current is None:
            current = pos["avg_cost"]  # fallback

        market_value = pos["shares"] * current
        pnl = market_value - pos["total_cost"]
        pnl_pct = pnl / pos["total_cost"] * 100

        total_value += market_value
        total_cost += pos["total_cost"]

        rows.append({
            "Ticker": t,
            "Shares": pos["shares"],
            "Avg Cost": f"${pos['avg_cost']:.2f}",
            "Current": f"${current:.2f}",
            "Mkt Value": f"${market_value:,.0f}",
            "P&L": f"{'+'if pnl>=0 else ''}${pnl:,.0f}",
            "P&L %": f"{'+'if pnl_pct>=0 else ''}{pnl_pct:.1f}%",
            "Days": (dt.date.today() - dt.date.fromisoformat(pos["entry_date"])).days,
        })

        # Stop-loss alert
        if pnl_pct / 100 <= STOP_LOSS_PCT:
            alerts.append(f"  🚨 STOP-LOSS HIT: {t} at {pnl_pct:.1f}% — SELL NOW")

        # Take profit suggestion
        if pnl_pct >= 15:
            alerts.append(f"  💰 TAKE PROFIT: {t} at +{pnl_pct:.1f}% — consider trimming")

    df = pd.DataFrame(rows)
    print(f"\n{df.to_string(index=False)}")

    # Alerts
    if alerts:
        print(f"\n{'=' * 70}")
        print("  ⚠️  ALERTS")
        print("=" * 70)
        for a in alerts:
            print(a)

    # Summary
    total_pnl = total_value - TOTAL_CAPITAL
    total_pnl_pct = total_pnl / TOTAL_CAPITAL * 100
    print(f"\n{'=' * 70}")
    print(f"  Cash:          ${pf['cash']:,.2f}")
    print(f"  Invested:      ${total_cost:,.2f}")
    print(f"  Market Value:  ${total_value:,.2f}")
    print(f"  Total P&L:     {'+'if total_pnl>=0 else ''}${total_pnl:,.2f} ({'+'if total_pnl_pct>=0 else ''}{total_pnl_pct:.2f}%)")
    print(f"  Positions:     {len(pf['positions'])}/{MAX_POSITIONS}")
    print("=" * 70)

    print_closed_trades(pf)


def print_closed_trades(pf: dict):
    """Print closed trade history."""
    closed = pf.get("closed_trades", [])
    if not closed:
        return

    print(f"\n  CLOSED TRADES ({len(closed)})")
    print("  " + "-" * 60)
    total_realized = 0
    for t in closed:
        sign = "+" if t["pnl"] >= 0 else ""
        print(f"  {t['ticker']:6s} | {sign}${t['pnl']:>10,.2f} ({sign}{t['pnl_pct']:.1f}%) | {t['entry_date']} → {t['exit_date']}")
        total_realized += t["pnl"]
    sign = "+" if total_realized >= 0 else ""
    print(f"  {'TOTAL':6s} | {sign}${total_realized:>10,.2f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_usage():
    print("""
Usage: python portfolio_tracker.py <command> [args]

Commands:
  show                          Show current portfolio + live P&L
  buy  <TICKER> <SHARES> <PRICE>  Record a buy (after executing on Investopedia)
  sell <TICKER> <PRICE>           Record a sell / close position
  reset                         Reset portfolio to starting capital
""")


def main():
    pf = load_portfolio()

    if len(sys.argv) < 2:
        show_portfolio(pf)
        return

    cmd = sys.argv[1].lower()

    if cmd == "show":
        show_portfolio(pf)

    elif cmd == "buy":
        if len(sys.argv) != 5:
            print("Usage: python portfolio_tracker.py buy <TICKER> <SHARES> <PRICE>")
            sys.exit(1)
        ticker = sys.argv[2].upper()
        shares = int(sys.argv[3])
        price = float(sys.argv[4])
        pf = add_position(pf, ticker, shares, price)
        save_portfolio(pf)

    elif cmd == "sell":
        if len(sys.argv) != 4:
            print("Usage: python portfolio_tracker.py sell <TICKER> <PRICE>")
            sys.exit(1)
        ticker = sys.argv[2].upper()
        price = float(sys.argv[3])
        pf = close_position(pf, ticker, price)
        save_portfolio(pf)

    elif cmd == "reset":
        pf = {
            "created": dt.datetime.now().isoformat(),
            "starting_capital": TOTAL_CAPITAL,
            "cash": TOTAL_CAPITAL,
            "positions": [],
            "closed_trades": [],
        }
        save_portfolio(pf)
        print("[OK] Portfolio reset.")

    else:
        print_usage()


if __name__ == "__main__":
    main()
