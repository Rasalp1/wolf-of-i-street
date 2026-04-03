#!/usr/bin/env python3
"""
run_morning.py — One-command daily workflow

Runs the full morning pipeline:
  1. Screen S&P 500 stocks
  2. Analyze top 10 with Claude
  3. Show current portfolio status
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run_step(label: str, script: str, args: list[str] | None = None):
    cmd = [sys.executable, str(ROOT / script)] + (args or [])
    print(f"\n{'━' * 60}")
    print(f"  STEP: {label}")
    print(f"{'━' * 60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"[WARN] {script} exited with code {result.returncode}")


def main():
    run_step("Screen S&P 500", "morning_screener.py")
    run_step("Analyze Top Candidates", "analyze_candidates.py")
    run_step("Portfolio Status", "portfolio_tracker.py", ["show"])
    print(f"\n{'━' * 60}")
    print("  ✅ Morning workflow complete!")
    print(f"{'━' * 60}\n")


if __name__ == "__main__":
    main()
