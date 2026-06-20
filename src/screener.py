"""
Parallel batch screener — calculates Trend Template for all stocks,
filters >= 8/9, returns Top N sorted by RS.
"""
from __future__ import annotations

import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np

from tvDatafeed import TvDatafeed, Interval
from .config import EXCHANGES

logger = logging.getLogger(__name__)


@dataclass
class ScreenResult:
    symbol: str
    exchange: str
    name: str
    sector: str
    trend_score: int        # 0-9
    rs_value: float         # 0-100
    rs_rating: str          # Leader/Strong/Average/Weak
    current_price: float
    distance_from_high: float   # % below 52wk high (negative = below)
    ma50: float
    ma150: float
    ma200: float
    high52w: float
    low52w: float
    volume_ratio: float     # latest vol / avg20vol
    conditions: list[bool]  # 9 trend template conditions


def screen_single(
    symbol: str,
    exchange: str,
    name: str,
    sector: str,
    index_closes: pd.Series,
) -> Optional[ScreenResult]:
    """Screen a single stock against Minervini Trend Template. Thread-safe."""
    try:
        tv = TvDatafeed()  # new instance per thread
        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_daily,
            n_bars=300,
        )
        if df is None or len(df) < 200:
            return None

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        ma50 = close.rolling(50).mean().iloc[-1]
        ma150 = close.rolling(150).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        ma200_21d_ago = close.rolling(200).mean().iloc[-21]

        price = close.iloc[-1]
        high52w = high.iloc[-252:].max() if len(high) >= 252 else high.max()
        low52w = low.iloc[-252:].min() if len(low) >= 252 else low.min()
        avg_vol20 = volume.iloc[-20:].mean()
        vol_ratio = volume.iloc[-1] / avg_vol20 if avg_vol20 > 0 else 1.0

        conditions = [
            bool(price > ma50),
            bool(price > ma150),
            bool(price > ma200),
            bool(ma50 > ma150),
            bool(ma50 > ma200),
            bool(ma150 > ma200),
            bool(close.rolling(200).mean().iloc[-1] > ma200_21d_ago),
            bool(price > low52w * 1.30),
            bool(price >= high52w * 0.75),
        ]
        trend_score = sum(conditions)

        # RS vs index (1M=20bars, 3M=63bars, 6M=126bars)
        def pct_return(series: pd.Series, bars: int) -> float:
            if len(series) < bars + 1:
                return 0.0
            return float((series.iloc[-1] / series.iloc[-bars] - 1) * 100)

        stock_1m = pct_return(close, 20)
        stock_3m = pct_return(close, 63)
        stock_6m = pct_return(close, 126)

        idx_1m = pct_return(index_closes, 20)
        idx_3m = pct_return(index_closes, 63)
        idx_6m = pct_return(index_closes, 126)

        def rs_score(stock_ret: float, idx_ret: float) -> float:
            if idx_ret == 0:
                return 50.0
            ratio = stock_ret / idx_ret
            return max(0.0, min(100.0, ratio * 50))

        rs = (
            rs_score(stock_1m, idx_1m) * 0.20
            + rs_score(stock_3m, idx_3m) * 0.30
            + rs_score(stock_6m, idx_6m) * 0.50
        )

        rs_rating = (
            "Leader" if rs >= 90 else
            "Strong" if rs >= 80 else
            "Average" if rs >= 60 else
            "Weak"
        )

        dist_from_high = (price / high52w - 1) * 100

        return ScreenResult(
            symbol=symbol,
            exchange=exchange,
            name=name,
            sector=sector,
            trend_score=trend_score,
            rs_value=round(rs, 1),
            rs_rating=rs_rating,
            current_price=round(float(price), 2),
            distance_from_high=round(float(dist_from_high), 1),
            ma50=round(float(ma50), 2),
            ma150=round(float(ma150), 2),
            ma200=round(float(ma200), 2),
            high52w=round(float(high52w), 2),
            low52w=round(float(low52w), 2),
            volume_ratio=round(float(vol_ratio), 2),
            conditions=conditions,
        )
    except Exception as e:
        logger.debug(f"Skip {symbol}: {e}")
        return None


def run_screener(
    tickers: list[tuple[str, str, str, str]],  # (symbol, exchange, name, sector)
    index_symbol: str,
    index_exchange: str,
    min_trend: int = 8,
    top_n: int = 20,
    max_workers: int = 10,
) -> list[ScreenResult]:
    """
    Run the full screener pipeline:
    1. Fetch index data once (sequential)
    2. Fetch all stocks in parallel
    3. Filter by min_trend score
    4. Sort by RS descending, return top_n
    """
    # 1. fetch index data once (sequential)
    tv = TvDatafeed()
    index_df = tv.get_hist(
        symbol=index_symbol,
        exchange=index_exchange,
        interval=Interval.in_daily,
        n_bars=300,
    )
    if index_df is None or len(index_df) < 20:
        raise RuntimeError(
            f"Could not fetch index data for {index_symbol}:{index_exchange}"
        )
    index_closes = index_df['close']

    # 2. parallel fetch all stocks
    results: list[ScreenResult] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(screen_single, sym, exch, name, sector, index_closes): sym
            for sym, exch, name, sector in tickers
        }

        total = len(futures)
        done = 0

        for future in as_completed(futures):
            done += 1
            sym = futures[future]
            try:
                result = future.result()
            except Exception as e:
                logger.debug(f"Future error for {sym}: {e}")
                result = None

            if result:
                results.append(result)
                status = f"OK {sym} trend={result.trend_score}/9 RS={result.rs_value}"
            else:
                failed += 1
                status = f"-- {sym}"

            # progress line
            print(f"\r[{done}/{total}] {status:<55}", end="", flush=True)
            time.sleep(0.05)  # tiny delay to avoid overwhelming TV

    print()  # newline after progress

    logger.info(
        f"Screened {total} stocks: {len(results)} fetched, {failed} failed"
    )

    # 3. filter >= min_trend
    qualified = [r for r in results if r.trend_score >= min_trend]

    # 4. sort by RS descending, then take top_n
    qualified.sort(key=lambda r: r.rs_value, reverse=True)
    return qualified[:top_n]
