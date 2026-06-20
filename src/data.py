from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd
import yfinance as yf
from tvDatafeed import TvDatafeed, Interval

warnings.filterwarnings('ignore')


def fetch_ohlcv(symbol: str, exchange: str, n_bars: int = 300) -> pd.DataFrame:
    """Fetch daily OHLCV data from TradingView via tvDatafeed."""
    tv = TvDatafeed()
    df = tv.get_hist(
        symbol=symbol,
        exchange=exchange,
        interval=Interval.in_daily,
        n_bars=n_bars,
    )
    if df is None or df.empty:
        raise RuntimeError(
            f"tvDatafeed returned no data for {symbol}:{exchange}. "
            "Check symbol/exchange spelling or network connectivity."
        )
    df = df[['open', 'high', 'low', 'close', 'volume']].copy()
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    return df


def fetch_tv_indicators(symbol: str, screener: str, exchange: str) -> dict:
    """Fetch technical indicator summary from tradingview-ta."""
    from tradingview_ta import TA_Handler, Interval as TAInterval

    handler = TA_Handler(
        symbol=symbol,
        screener=screener,
        exchange=exchange,
        interval=TAInterval.INTERVAL_1_DAY,
    )
    try:
        analysis = handler.get_analysis()
        return {
            'indicators': analysis.indicators,
            'summary': analysis.summary,
        }
    except Exception as exc:
        # TV-TA sometimes 404s on thinly-traded symbols; treat as empty.
        return {'indicators': {}, 'summary': {}}


def fetch_fundamentals(symbol: str, yf_suffix: str) -> dict:
    """
    Fetch fundamental data from yfinance.
    Returns a dict; missing fields are None so callers must guard.
    """
    ticker_sym = f"{symbol}{yf_suffix}"
    ticker = yf.Ticker(ticker_sym)

    info: dict = {}
    try:
        info = ticker.info or {}
    except Exception:
        pass

    # Annual earnings history for YoY EPS growth
    earnings_df: Optional[pd.DataFrame] = None
    try:
        earnings_df = ticker.earnings  # type: ignore[attr-defined]
        if earnings_df is not None and earnings_df.empty:
            earnings_df = None
    except Exception:
        pass

    # Quarterly financials for revenue trend
    quarterly_financials: Optional[pd.DataFrame] = None
    try:
        quarterly_financials = ticker.quarterly_financials  # type: ignore[attr-defined]
        if quarterly_financials is not None and quarterly_financials.empty:
            quarterly_financials = None
    except Exception:
        pass

    # Institutional holders table
    institutional_holders: Optional[pd.DataFrame] = None
    try:
        institutional_holders = ticker.institutional_holders  # type: ignore[attr-defined]
        if institutional_holders is not None and institutional_holders.empty:
            institutional_holders = None
    except Exception:
        pass

    return {
        'info': info,
        'earnings_df': earnings_df,
        'quarterly_financials': quarterly_financials,
        'institutional_holders': institutional_holders,
    }
