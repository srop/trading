#!/usr/bin/env python3
"""
SEPA (Mark Minervini) Trading Analysis System
Usage:
    python main.py NVDA NASDAQ
    python main.py PTT SET
    python main.py KBANK SET --portfolio 500000 --risk 0.005
"""
from __future__ import annotations

import argparse
import sys
import traceback

from src.analyzer import run_analysis
from src.scoring import calculate_score
from src.output import print_output
from src.config import PORTFOLIO_SIZE, RISK_PERCENT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='SEPA (Mark Minervini) stock analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('symbol', type=str, help='Ticker symbol (e.g. NVDA, PTT)')
    parser.add_argument(
        'exchange',
        type=str,
        help='Exchange (NASDAQ | NYSE | SET)',
    )
    parser.add_argument(
        '--portfolio',
        type=float,
        default=PORTFOLIO_SIZE,
        metavar='SIZE',
        help=f'Portfolio size in local currency (default: {PORTFOLIO_SIZE:,.0f})',
    )
    parser.add_argument(
        '--risk',
        type=float,
        default=RISK_PERCENT,
        metavar='PCT',
        help=f'Risk per trade as decimal (default: {RISK_PERCENT} = 1%%)',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    symbol: str = args.symbol.upper()
    exchange: str = args.exchange.upper()

    print(f'\nFetching data for {symbol} ({exchange}) …')

    try:
        result = run_analysis(
            symbol=symbol,
            exchange=exchange,
            portfolio_size=args.portfolio,
            risk_percent=args.risk,
        )
    except ValueError as exc:
        print(f'\n[ERROR] {exc}', file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f'\n[DATA ERROR] {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'\n[UNEXPECTED ERROR] {exc}', file=sys.stderr)
        traceback.print_exc()
        return 1

    score = calculate_score(result)
    print_output(result, score)
    return 0


if __name__ == '__main__':
    sys.exit(main())
