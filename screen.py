#!/usr/bin/env python3
"""
SEPA Stock Screener
Usage:
    python screen.py SET
    python screen.py NASDAQ
    python screen.py all
    python screen.py SET --workers 15 --top 20 --min-trend 8
    python screen.py NASDAQ --no-ai    # skip AI analysis
"""
from __future__ import annotations

import argparse
import csv
import logging
logging.getLogger('tvDatafeed').setLevel(logging.ERROR)
import sys
from pathlib import Path

from src.screener import run_screener
from src.ai_analyst import analyze_with_ai
from src.config import OPENROUTER_API_KEY


DATA_DIR = Path(__file__).parent / "data"


def load_csv(filename: str, exchange_override: str = None) -> list[tuple]:
    """Load tickers from a CSV file in the data directory."""
    path = DATA_DIR / filename
    tickers = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            sym = row["symbol"].strip().upper()
            exch = (
                exchange_override
                if exchange_override
                else row.get("exchange", "").strip().upper()
            )
            name = row.get("name", sym)
            sector = row.get("sector", "Unknown")
            tickers.append((sym, exch, name, sector))
    return tickers


def print_screener_results(results: list, exchange_label: str) -> None:
    """Print a formatted table of screener results."""
    print(f"\n{'='*68}")
    print(f"  SCREENER RESULTS — {exchange_label}  (Top {len(results)} by RS)")
    print(f"{'='*68}")
    print(
        f"{'#':>2}  {'Symbol':<8} {'Trend':>6} {'RS':>6} {'Rating':<8}"
        f" {'Dist 52wkH':>10}  Sector"
    )
    print(f"{'-'*68}")
    for i, r in enumerate(results, 1):
        print(
            f"{i:2}. {r.symbol:<8} {r.trend_score}/9   {r.rs_value:>5.1f}"
            f"  {r.rs_rating:<8} {r.distance_from_high:>+8.1f}%  {r.sector}"
        )
    print(f"{'='*68}\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SEPA Stock Screener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "market",
        choices=["SET", "NASDAQ", "COMMODITIES", "all"],
        help="Market to screen",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Parallel workers (default: 10)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Top N stocks to show and send to AI (default: 20)",
    )
    parser.add_argument(
        "--min-trend",
        type=int,
        default=8,
        help="Minimum trend template score 0-9 (default: 8)",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI analysis step",
    )
    args = parser.parse_args()

    all_results = []

    if args.market in ("SET", "all"):
        print(f"\nScreening SET100 ({args.workers} parallel workers)...")
        set_tickers = load_csv("set100_stocks.csv", exchange_override="SET")
        set_results = run_screener(
            tickers=set_tickers,
            index_symbol="SET50",
            index_exchange="SET",
            min_trend=args.min_trend,
            top_n=args.top,
            max_workers=args.workers,
        )
        print_screener_results(set_results, "SET")
        all_results.extend(set_results)

    if args.market in ("NASDAQ", "all"):
        print(f"\nScreening NASDAQ100 ({args.workers} parallel workers)...")
        nasdaq_tickers = load_csv("nasdaq100_stocks.csv", exchange_override="NASDAQ")
        nasdaq_results = run_screener(
            tickers=nasdaq_tickers,
            index_symbol="SPY",
            index_exchange="AMEX",
            min_trend=args.min_trend,
            top_n=args.top,
            max_workers=args.workers,
        )
        print_screener_results(nasdaq_results, "NASDAQ")
        all_results.extend(nasdaq_results)

    if args.market in ("COMMODITIES", "all"):
        print(f"\nScreening Commodities ETF ({args.workers} parallel workers)...")
        commodity_tickers = load_csv("commodities.csv", exchange_override="AMEX")
        commodity_results = run_screener(
            tickers=commodity_tickers,
            index_symbol="SPY",
            index_exchange="AMEX",
            min_trend=args.min_trend,
            top_n=args.top,
            max_workers=args.workers,
        )
        print_screener_results(commodity_results, "COMMODITIES")
        all_results.extend(commodity_results)

    if not all_results:
        print("No stocks passed the screen.")
        return 0

    # Sort combined results by RS descending for AI
    all_results.sort(key=lambda r: r.rs_value, reverse=True)
    top_for_ai = all_results[: args.top]

    if args.no_ai:
        print(f"Skipped AI analysis (--no-ai). {len(all_results)} stocks qualified.")
        return 0

    if not OPENROUTER_API_KEY:
        print("OPENROUTER_API_KEY not set in .env — skipping AI analysis")
        return 0

    print(f"\nSending Top {len(top_for_ai)} stocks to AI (OpenRouter)...\n")
    analysis = analyze_with_ai(top_for_ai)

    print("=" * 68)
    print("  AI SEPA ANALYSIS")
    print("=" * 68)
    print(analysis)
    print("=" * 68)

    return 0


if __name__ == "__main__":
    sys.exit(main())
