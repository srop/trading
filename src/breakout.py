"""
Intraday breakout detector for the SEPA trading system.

Provides two main components:
  - DailyCache: cached daily indicators per symbol (refreshed once per trading day)
  - BreakoutSignal: emitted when intraday 15-min bar satisfies all breakout conditions
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pytz
from tvDatafeed import TvDatafeed, Interval

logger = logging.getLogger(__name__)

# Suppress noisy tvDatafeed warnings
logging.getLogger('tvDatafeed').setLevel(logging.ERROR)

BKK = pytz.timezone('Asia/Bangkok')

# Module-level TvDatafeed instance — reused across all calls
_tv = TvDatafeed()


@dataclass
class DailyCache:
    pivot: float          # 50-day high (yesterday's close excluded, for cross detection)
    trend_score: int      # 0-9
    ma50: float
    ma150: float
    ma200: float
    avg_daily_vol: float  # avg volume over last 20 days
    high52w: float
    low52w: float
    fetched_date: str     # YYYY-MM-DD — used to check if cache is still valid


@dataclass
class BreakoutSignal:
    symbol: str
    exchange: str
    name: str
    sector: str
    current_price: float
    pivot: float
    distance_pct: float       # (current_price / pivot - 1) * 100
    vol_ratio: float          # current bar vol / expected per-bar vol
    trend_score: int
    bar_time: str             # timestamp of the 15-min bar that triggered


def build_daily_cache(symbol: str, exchange: str) -> Optional[DailyCache]:
    """
    Fetch 300 daily bars and compute all SEPA indicators needed for intraday scanning.
    Returns None if there is insufficient data (< 200 bars).
    """
    try:
        df = _tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_daily,
            n_bars=300,
        )
    except Exception as e:
        logger.debug(f"build_daily_cache: failed to fetch {symbol}:{exchange} — {e}")
        return None

    if df is None or len(df) < 200:
        return None

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # Pivot = yesterday's 50-day high (exclude today's bar so we detect crosses)
    pivot = float(df['high'].iloc[:-1].rolling(50).max().iloc[-1])

    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma150 = float(close.rolling(150).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    avg_daily_vol = float(volume.iloc[-20:].mean())

    high52w = float(high.iloc[-252:].max()) if len(high) >= 252 else float(high.max())
    low52w = float(low.iloc[-252:].min()) if len(low) >= 252 else float(low.min())

    # Trend Template: same 9 conditions as screener.py
    price = float(close.iloc[-1])
    ma200_21ago = float(close.rolling(200).mean().iloc[-22]) if len(close) >= 222 else float('nan')
    import numpy as np
    conditions = [
        price > ma50,
        price > ma150,
        price > ma200,
        ma50 > ma150,
        ma50 > ma200,
        ma150 > ma200,
        (ma200 > ma200_21ago) if not np.isnan(ma200_21ago) else False,
        price >= low52w * 1.30,
        price >= high52w * 0.75,
    ]
    trend_score = sum(bool(c) for c in conditions)

    fetched_date = datetime.now(BKK).strftime("%Y-%m-%d")

    return DailyCache(
        pivot=pivot,
        trend_score=trend_score,
        ma50=ma50,
        ma150=ma150,
        ma200=ma200,
        avg_daily_vol=avg_daily_vol,
        high52w=high52w,
        low52w=low52w,
        fetched_date=fetched_date,
    )


def check_breakout(
    symbol: str,
    exchange: str,
    cache: DailyCache,
    bars_per_day: int,
) -> Optional[BreakoutSignal]:
    """
    Fetch the latest 15-min bars and check whether the most recent bar satisfies
    all four breakout conditions. Returns a BreakoutSignal on success, None otherwise.

    bars_per_day is used to normalise daily average volume to a per-bar expectation:
      SET    ~ 20 bars/day  (5h session / 15min)
      NASDAQ ~ 26 bars/day  (6.5h session / 15min)
    """
    try:
        df15 = _tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_15_minutes,
            n_bars=50,
        )
    except Exception as e:
        logger.debug(f"check_breakout: failed to fetch 15min data for {symbol}:{exchange} — {e}")
        return None

    if df15 is None or len(df15) == 0:
        return None

    current_price = float(df15['close'].iloc[-1])
    current_vol = float(df15['volume'].iloc[-1])
    bar_time = str(df15.index[-1])

    expected_vol = cache.avg_daily_vol / bars_per_day if bars_per_day > 0 else 1.0
    vol_ratio = current_vol / expected_vol if expected_vol > 0 else 0.0

    price_breakout = current_price > cache.pivot
    volume_surge = vol_ratio >= 1.5
    trend_ok = cache.trend_score >= 7
    not_extended = current_price <= cache.pivot * 1.10

    if not (price_breakout and volume_surge and trend_ok and not_extended):
        return None

    distance_pct = (current_price / cache.pivot - 1) * 100

    return BreakoutSignal(
        symbol=symbol,
        exchange=exchange,
        name=symbol,    # caller should overwrite with name from CSV
        sector="",      # caller should overwrite with sector from CSV
        current_price=current_price,
        pivot=cache.pivot,
        distance_pct=round(distance_pct, 2),
        vol_ratio=round(vol_ratio, 2),
        trend_score=cache.trend_score,
        bar_time=bar_time,
    )
