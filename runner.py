#!/usr/bin/env python3
"""
SEPA Intraday Runner — polls every 15 minutes during market hours,
detects breakouts across SET100 and NASDAQ100, runs full SEPA analysis,
and sends Telegram alerts.

Usage:
    python runner.py
"""
from __future__ import annotations

import csv
import logging
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

import pytz

# Suppress tvDatafeed noise early, before any tvDatafeed import
logging.getLogger('tvDatafeed').setLevel(logging.ERROR)

from src.breakout import build_daily_cache, check_breakout, DailyCache, BreakoutSignal
from src.sheets import get_open_positions, close_position
from src.exit_monitor import check_exit, format_exit_alert
from src.config import (
    SET_OPEN_AM_START, SET_OPEN_AM_END, SET_OPEN_PM_START, SET_OPEN_PM_END,
    NASDAQ_OPEN_START, NASDAQ_OPEN_END,
    GOLD_OPEN_START, GOLD_OPEN_END, GOLD_OPEN_WEEKENDS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Timezone constants
# ─────────────────────────────────────────────────────────────────────────────

BKK = pytz.timezone('Asia/Bangkok')
ET  = pytz.timezone('America/New_York')

# ─────────────────────────────────────────────────────────────────────────────
# Market hours
# ─────────────────────────────────────────────────────────────────────────────

def _parse_time(s: str) -> dtime:
    h, m = s.split(':')
    return dtime(int(h), int(m))


def is_set_open() -> bool:
    now = datetime.now(BKK)
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning   = _parse_time(SET_OPEN_AM_START) <= t <= _parse_time(SET_OPEN_AM_END)
    afternoon = _parse_time(SET_OPEN_PM_START) <= t <= _parse_time(SET_OPEN_PM_END)
    return morning or afternoon


def is_nasdaq_open() -> bool:
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return _parse_time(NASDAQ_OPEN_START) <= t <= _parse_time(NASDAQ_OPEN_END)


def is_gold_open() -> bool:
    now = datetime.now(BKK)
    if now.weekday() >= 5 and not GOLD_OPEN_WEEKENDS:
        return False
    return _parse_time(GOLD_OPEN_START) <= now.time() <= _parse_time(GOLD_OPEN_END)

# ─────────────────────────────────────────────────────────────────────────────
# Daily cache management
# ─────────────────────────────────────────────────────────────────────────────

def get_or_refresh_cache(
    symbol: str,
    exchange: str,
    cache_store: dict,
) -> Optional[DailyCache]:
    """
    Return a valid DailyCache for symbol:exchange.
    If absent or stale (fetched_date != today Bangkok), fetch fresh data.
    """
    key = f"{symbol}:{exchange}"
    today = datetime.now(BKK).strftime("%Y-%m-%d")
    existing = cache_store.get(key)
    if existing and existing.fetched_date == today:
        return existing
    fresh = build_daily_cache(symbol, exchange)
    if fresh:
        cache_store[key] = fresh
    return fresh

# ─────────────────────────────────────────────────────────────────────────────
# Ticker loading
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"


def load_tickers(filename: str, exchange: str = "") -> list[tuple]:
    """
    Read a CSV from the data directory and return list of
    (symbol, exchange, name, sector) tuples.
    exchange override ถ้าไม่ส่งมา จะอ่านจาก column 'exchange' ใน CSV แทน
    """
    path = DATA_DIR / filename
    tickers = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            sym = row["symbol"].strip().upper()
            exch = exchange or row.get("exchange", "").strip().upper()
            name = row.get("name", sym)
            sector = row.get("sector", "Unknown")
            tickers.append((sym, exch, name, sector))
    return tickers

# ─────────────────────────────────────────────────────────────────────────────
# Signal handling
# ─────────────────────────────────────────────────────────────────────────────

def handle_signal(signal: BreakoutSignal) -> None:
    """Run full SEPA analysis and send a Telegram alert for a confirmed breakout."""
    # Lazy imports to avoid circular dependencies and slow startup
    from webhook.analysis import run_breakout_analysis
    from webhook.telegram import send_alert, format_alert

    webhook_data = {
        'ticker': signal.symbol,
        'exchange': signal.exchange,
        'close': signal.current_price,
        'pivot': signal.pivot,
        'vol_ratio': signal.vol_ratio,
        'trend_score': signal.trend_score,
    }
    try:
        result, scored, ai_summary = run_breakout_analysis(
            signal.symbol, signal.exchange, webhook_data
        )
        msg = format_alert(result, scored, ai_summary)
        send_alert(msg)
        logging.info(f"Alert sent: {signal.symbol} score={scored.confidence_score:.0f}")
    except Exception as e:
        logging.error(f"Analysis failed for {signal.symbol}: {e}")
        from webhook.telegram import send_alert  # noqa: F811
        send_alert(
            f"⚠️ <b>Breakout detected but analysis failed</b>\n"
            f"{signal.symbol} ({signal.exchange})\n"
            f"<code>{str(e)[:200]}</code>"
        )

# ─────────────────────────────────────────────────────────────────────────────
# Market scan
# ─────────────────────────────────────────────────────────────────────────────

def check_exits() -> None:
    """Check all open positions for exit conditions and send alerts."""
    from webhook.telegram import send_alert

    try:
        positions = get_open_positions()
    except Exception as e:
        logging.error(f"Failed to load positions for exit check: {e}")
        return

    for pos in positions:
        try:
            signal = check_exit(pos)
            if signal:
                msg = format_exit_alert(signal)
                send_alert(msg)
                if signal.action == 'SELL NOW':
                    close_position(pos, signal.current_price, signal.reason)
                logging.info(
                    f"Exit signal: {pos.symbol} {signal.reason} {signal.pnl_pct:+.1f}%"
                )
        except Exception as e:
            logging.error(f"Exit check failed {pos.symbol}: {e}")


def scan_market(
    tickers: list[tuple],
    cache_store: dict,
    alerted_today: set,
    bars_per_day: int,
    label: str,
) -> list[BreakoutSignal]:
    """Scan one market's stocks for breakouts. Returns list of BreakoutSignal."""
    signals = []
    today_str = datetime.now(BKK).strftime("%Y-%m-%d")

    for symbol, exchange, name, sector in tickers:
        try:
            cache = get_or_refresh_cache(symbol, exchange, cache_store)
            if not cache:
                continue

            key_today = f"{symbol}:{exchange}:{today_str}"
            if key_today in alerted_today:
                continue  # already alerted for this symbol today

            signal = check_breakout(symbol, exchange, cache, bars_per_day)
            if signal:
                signal.name = name
                signal.sector = sector
                signals.append(signal)
                alerted_today.add(key_today)
        except Exception as e:
            logging.debug(f"Skip {symbol}: {e}")

    return signals

# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

POLL_SECONDS = 15 * 60
SET_BARS_PER_DAY    = 20   # 5h session / 15min bars
NASDAQ_BARS_PER_DAY = 26   # 6.5h session / 15min bars
MAX_ALERTS_PER_MARKET = 10  # cap per scan cycle, sorted by vol_ratio desc


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    set_tickers        = load_tickers('set100_stocks.csv',    'SET')
    nasdaq_tickers     = load_tickers('nasdaq100_stocks.csv', 'NASDAQ')
    commodity_tickers  = load_tickers('commodities.csv')  # exchange อ่านจาก CSV

    cache_store: dict   = {}   # shared daily cache across all scans
    alerted_today: set  = set()

    logging.info("SEPA Runner started — polling every 15 minutes")

    while True:
        now_bkk = datetime.now(BKK)
        today_str = now_bkk.strftime("%Y-%m-%d")

        # Trim stale dedup keys that don't belong to today
        alerted_today = {k for k in alerted_today if today_str in k}

        scanned = False

        if is_set_open():
            logging.info("Scanning SET100...")
            signals = scan_market(
                set_tickers, cache_store, alerted_today, SET_BARS_PER_DAY, "SET"
            )
            signals = sorted(signals, key=lambda s: s.vol_ratio, reverse=True)[:MAX_ALERTS_PER_MARKET]
            for sig in signals:
                logging.info(f"BREAKOUT: {sig.symbol} (SET) price={sig.current_price} vol={sig.vol_ratio:.1f}x")
                handle_signal(sig)
            logging.info(f"SET scan done — {len(signals)} breakout(s) sent")
            scanned = True

        if is_nasdaq_open():
            logging.info("Scanning NASDAQ100...")
            signals = scan_market(
                nasdaq_tickers, cache_store, alerted_today, NASDAQ_BARS_PER_DAY, "NASDAQ"
            )
            signals = sorted(signals, key=lambda s: s.vol_ratio, reverse=True)[:MAX_ALERTS_PER_MARKET]
            for sig in signals:
                logging.info(f"BREAKOUT: {sig.symbol} (NASDAQ) price={sig.current_price} vol={sig.vol_ratio:.1f}x")
                handle_signal(sig)
            logging.info(f"NASDAQ scan done — {len(signals)} breakout(s) sent")
            scanned = True

        if is_gold_open():
            logging.info("Scanning Commodities & Gold (08:00–21:00 BKK)...")
            signals = scan_market(
                commodity_tickers, cache_store, alerted_today, NASDAQ_BARS_PER_DAY, "COMMODITIES"
            )
            signals = sorted(signals, key=lambda s: s.vol_ratio, reverse=True)[:MAX_ALERTS_PER_MARKET]
            for sig in signals:
                logging.info(f"BREAKOUT: {sig.symbol} (Commodity) price={sig.current_price} vol={sig.vol_ratio:.1f}x")
                handle_signal(sig)
            logging.info(f"Commodities scan done — {len(signals)} breakout(s) sent")
            scanned = True

        if scanned:
            logging.info("Checking exit conditions for open positions...")
            check_exits()

        if not scanned:
            next_check = now_bkk.strftime("%H:%M")
            logging.info(f"Markets closed — next check in 15 min ({next_check})")

        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    main()
