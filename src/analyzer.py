from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .data import fetch_ohlcv, fetch_tv_indicators, fetch_fundamentals
from .config import EXCHANGES, PORTFOLIO_SIZE, RISK_PERCENT


# ─────────────────────────────────────────────────────────────────────────────
# Result containers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MarketResult:
    condition: str          # "Bullish" | "Neutral" | "Bearish"
    is_bear: bool
    index_price: float
    ma50: float
    ma200: float


@dataclass
class TrendResult:
    conditions_met: int     # 0-9
    total: int = 9
    details: list[bool] = field(default_factory=list)
    passed: bool = False    # True only if >= 7/9


@dataclass
class RSResult:
    rs_1m: float
    rs_3m: float
    rs_6m: float
    rs_avg: float
    rating: str             # "Leader" | "Strong" | "Average" | "Weak"


@dataclass
class FundamentalResult:
    eps_growth_pct: Optional[float]
    eps_rating: str          # "Excellent" | "Strong" | "Weak" | "N/A"
    revenue_growth_pct: Optional[float]
    revenue_rating: str
    roe_pct: Optional[float]
    roe_rating: str
    annual_eps_growth_pct: Optional[float]
    annual_eps_rating: str
    margin_trend: str        # "Improving" | "Stable" | "Declining" | "N/A"
    available: bool          # False if yfinance returned nothing useful


@dataclass
class InstitutionalResult:
    pct_held: Optional[float]
    rating: str              # "Positive" | "Neutral" | "Negative"
    available: bool


@dataclass
class BasePatternResult:
    pattern: str             # "Cup with Handle" | "Flat Base" | "Double Bottom" | "None"
    detail: str


@dataclass
class VCPResult:
    rating: str              # "Excellent" | "Good" | "Weak" | "None"
    contracting_segments: int
    volume_decreasing: bool


@dataclass
class TightActionResult:
    rating: str              # "Excellent" | "Good" | "Weak"
    avg_range_pct: float


@dataclass
class PocketPivotResult:
    found: bool
    date: Optional[str]
    volume_ratio: Optional[float]


@dataclass
class BreakoutResult:
    pivot_price: float
    current_price: float
    distance_pct: float
    breakout_volume_ratio: float
    avg_vol_20: float
    rating: str              # "Excellent" | "Good" | "Weak" | "Not Yet"
    extended: bool
    action: str


@dataclass
class PositionResult:
    portfolio_size: float
    risk_amount: float
    stop_loss: float
    stop_pct: float
    risk_per_share: float
    position_size: int
    entry_low: float
    entry_high: float
    target1: float
    target2: float
    risk_reward: float


@dataclass
class SEPAResult:
    symbol: str
    exchange: str
    current_price: float
    market: MarketResult
    trend: TrendResult
    rs: RSResult
    fundamental: FundamentalResult
    institutional: InstitutionalResult
    base_pattern: BasePatternResult
    vcp: VCPResult
    tight_action: TightActionResult
    pocket_pivot: PocketPivotResult
    breakout: BreakoutResult
    position: PositionResult


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _ma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def _safe_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(value)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 – Market Direction
# ─────────────────────────────────────────────────────────────────────────────

def analyze_market(index_symbol: str, index_exchange: str) -> MarketResult:
    try:
        df = fetch_ohlcv(index_symbol, index_exchange, n_bars=300)
    except RuntimeError:
        # SET50 may not be available on TradingView free tier; fall back gracefully.
        return MarketResult(
            condition='Neutral',
            is_bear=False,
            index_price=float('nan'),
            ma50=float('nan'),
            ma200=float('nan'),
        )

    close = df['close']
    ma50_series = _ma(close, 50)
    ma200_series = _ma(close, 200)

    price = close.iloc[-1]
    ma50 = ma50_series.iloc[-1]
    ma200 = ma200_series.iloc[-1]

    if any(np.isnan([price, ma50, ma200])):
        return MarketResult(condition='Neutral', is_bear=False,
                            index_price=price, ma50=ma50, ma200=ma200)

    if price > ma50 and ma50 > ma200:
        condition = 'Bullish'
        is_bear = False
    elif price < ma200:
        condition = 'Bearish'
        is_bear = True
    else:
        condition = 'Neutral'
        is_bear = False

    return MarketResult(condition=condition, is_bear=is_bear,
                        index_price=price, ma50=ma50, ma200=ma200)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 – Trend Template (9 conditions)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_trend(df: pd.DataFrame) -> TrendResult:
    close = df['close']
    n = len(close)

    ma50_s = _ma(close, 50)
    ma150_s = _ma(close, 150)
    ma200_s = _ma(close, 200)

    price = close.iloc[-1]
    ma50 = ma50_s.iloc[-1]
    ma150 = ma150_s.iloc[-1]
    ma200 = ma200_s.iloc[-1]

    # MA200 slope: compare today vs 21 trading days ago
    ma200_21ago = ma200_s.iloc[-22] if n >= 222 else float('nan')

    low_52wk = close.rolling(252, min_periods=50).min().iloc[-1]
    high_52wk = close.rolling(252, min_periods=50).max().iloc[-1]

    checks = [
        price > ma50,
        price > ma150,
        price > ma200,
        ma50 > ma150,
        ma50 > ma200,
        ma150 > ma200,
        (ma200 > ma200_21ago) if not np.isnan(ma200_21ago) else False,
        price >= low_52wk * 1.30,
        price >= high_52wk * 0.75,
    ]

    # Replace NaN-driven False with explicit False
    checks = [bool(c) if not (isinstance(c, float) and np.isnan(c)) else False
              for c in checks]

    met = sum(checks)
    return TrendResult(
        conditions_met=met,
        total=9,
        details=checks,
        passed=(met >= 7),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 – Relative Strength
# ─────────────────────────────────────────────────────────────────────────────

def _period_return(close: pd.Series, days: int) -> float:
    if len(close) < days + 1:
        return float('nan')
    return (close.iloc[-1] / close.iloc[-(days + 1)] - 1.0)


def analyze_rs(stock_df: pd.DataFrame, index_df: pd.DataFrame) -> RSResult:
    sc = stock_df['close']
    ic = index_df['close']

    def relative_strength(s_ret: float, i_ret: float) -> float:
        if np.isnan(s_ret) or np.isnan(i_ret) or i_ret == 0:
            return 50.0
        # Normalise to 0-100 scale anchored at 50 (index = 50)
        return (s_ret / abs(i_ret)) * 50.0 + 50.0

    rs_1m = relative_strength(_period_return(sc, 21), _period_return(ic, 21))
    rs_3m = relative_strength(_period_return(sc, 63), _period_return(ic, 63))
    rs_6m = relative_strength(_period_return(sc, 126), _period_return(ic, 126))

    # Weighted average: 20% 1M, 30% 3M, 50% 6M
    rs_avg = 0.20 * rs_1m + 0.30 * rs_3m + 0.50 * rs_6m
    rs_avg = max(0.0, min(100.0, rs_avg))

    if rs_avg >= 90:
        rating = 'Leader'
    elif rs_avg >= 80:
        rating = 'Strong'
    elif rs_avg >= 60:
        rating = 'Average'
    else:
        rating = 'Weak'

    return RSResult(rs_1m=rs_1m, rs_3m=rs_3m, rs_6m=rs_6m,
                    rs_avg=rs_avg, rating=rating)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 – Fundamentals
# ─────────────────────────────────────────────────────────────────────────────

def _eps_rating(pct: Optional[float]) -> str:
    if pct is None:
        return 'N/A'
    if pct >= 30:
        return 'Excellent'
    if pct >= 20:
        return 'Strong'
    return 'Weak'


def _rev_rating(pct: Optional[float]) -> str:
    if pct is None:
        return 'N/A'
    if pct >= 25:
        return 'Excellent'
    if pct >= 20:
        return 'Strong'
    return 'Weak'


def _roe_rating(pct: Optional[float]) -> str:
    if pct is None:
        return 'N/A'
    return 'Excellent' if pct >= 17 else 'Weak'


def _annual_eps_rating(pct: Optional[float]) -> str:
    if pct is None:
        return 'N/A'
    if pct >= 25:
        return 'Excellent'
    if pct >= 15:
        return 'Strong'
    return 'Weak'


def analyze_fundamentals(fund_data: dict) -> FundamentalResult:
    info = fund_data.get('info', {})
    earnings_df: Optional[pd.DataFrame] = fund_data.get('earnings_df')
    quarterly_financials: Optional[pd.DataFrame] = fund_data.get('quarterly_financials')

    available = bool(info)

    # ── Trailing EPS Growth (YoY) ──────────────────────────────────────────
    eps_growth: Optional[float] = None
    trailing_eps = _safe_float(info.get('trailingEps'))
    if earnings_df is not None and len(earnings_df) >= 2:
        try:
            eps_vals = earnings_df['Earnings'].dropna()
            if len(eps_vals) >= 2:
                latest = float(eps_vals.iloc[-1])
                prev = float(eps_vals.iloc[-2])
                if prev and prev != 0:
                    eps_growth = (latest - prev) / abs(prev) * 100.0
        except Exception:
            pass

    # Fallback: use epsForward vs trailingEps from info
    if eps_growth is None and trailing_eps is not None:
        fwd_eps = _safe_float(info.get('forwardEps'))
        if fwd_eps is not None and trailing_eps != 0:
            eps_growth = (fwd_eps - trailing_eps) / abs(trailing_eps) * 100.0

    # ── Revenue Growth ─────────────────────────────────────────────────────
    revenue_growth: Optional[float] = None
    rev_growth_raw = _safe_float(info.get('revenueGrowth'))
    if rev_growth_raw is not None:
        revenue_growth = rev_growth_raw * 100.0

    if revenue_growth is None and quarterly_financials is not None:
        try:
            rev_row = quarterly_financials.loc['Total Revenue'].dropna()
            if len(rev_row) >= 2:
                latest_rev = float(rev_row.iloc[0])
                prev_rev = float(rev_row.iloc[1])
                if prev_rev and prev_rev != 0:
                    revenue_growth = (latest_rev - prev_rev) / abs(prev_rev) * 100.0
        except Exception:
            pass

    # ── ROE ───────────────────────────────────────────────────────────────
    roe: Optional[float] = None
    roe_raw = _safe_float(info.get('returnOnEquity'))
    if roe_raw is not None:
        roe = roe_raw * 100.0

    # ── Annual EPS Growth ─────────────────────────────────────────────────
    annual_eps_growth: Optional[float] = None
    if earnings_df is not None and len(earnings_df) >= 2:
        try:
            eps_vals = earnings_df['Earnings'].dropna()
            if len(eps_vals) >= 2:
                latest = float(eps_vals.iloc[-1])
                prev = float(eps_vals.iloc[-2])
                if prev and prev != 0:
                    annual_eps_growth = (latest - prev) / abs(prev) * 100.0
        except Exception:
            pass

    # ── Margin Trend ──────────────────────────────────────────────────────
    margin_trend = 'N/A'
    current_margin = _safe_float(info.get('profitMargins'))
    if current_margin is not None:
        # Use gross margins as a proxy for trend direction when only one data point
        trailing_margin = _safe_float(info.get('grossMargins'))
        if trailing_margin is not None:
            if current_margin > trailing_margin * 1.02:
                margin_trend = 'Improving'
            elif current_margin < trailing_margin * 0.98:
                margin_trend = 'Declining'
            else:
                margin_trend = 'Stable'
        else:
            margin_trend = 'Stable'

    return FundamentalResult(
        eps_growth_pct=eps_growth,
        eps_rating=_eps_rating(eps_growth),
        revenue_growth_pct=revenue_growth,
        revenue_rating=_rev_rating(revenue_growth),
        roe_pct=roe,
        roe_rating=_roe_rating(roe),
        annual_eps_growth_pct=annual_eps_growth,
        annual_eps_rating=_annual_eps_rating(annual_eps_growth),
        margin_trend=margin_trend,
        available=available,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 – Institutional Sponsorship
# ─────────────────────────────────────────────────────────────────────────────

def analyze_institutional(fund_data: dict) -> InstitutionalResult:
    info = fund_data.get('info', {})
    holders_df: Optional[pd.DataFrame] = fund_data.get('institutional_holders')

    pct_held: Optional[float] = None

    raw = _safe_float(info.get('institutionsPercentHeld'))
    if raw is not None:
        pct_held = raw * 100.0

    # Fallback: sum % Held column from institutional_holders table
    if pct_held is None and holders_df is not None:
        try:
            col = [c for c in holders_df.columns if 'held' in c.lower() or '%' in c.lower()]
            if col:
                pct_held = float(holders_df[col[0]].sum()) * 100.0
        except Exception:
            pass

    if pct_held is None:
        return InstitutionalResult(pct_held=None, rating='Neutral', available=False)

    if pct_held >= 30:
        rating = 'Positive'
    elif pct_held >= 10:
        rating = 'Neutral'
    else:
        rating = 'Negative'

    return InstitutionalResult(pct_held=pct_held, rating=rating, available=True)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 – Base Pattern Detection
# ─────────────────────────────────────────────────────────────────────────────

def analyze_base_pattern(df: pd.DataFrame) -> BasePatternResult:
    recent = df.tail(60).copy()
    close = recent['close'].values
    n = len(close)
    if n < 25:
        return BasePatternResult(pattern='None', detail='Insufficient data')

    max_c = float(np.max(close))
    min_c = float(np.min(close))

    # ── Flat Base: range <= 15% over at least 25 bars ─────────────────────
    flat_range = (max_c - min_c) / max_c
    if flat_range <= 0.15 and n >= 25:
        return BasePatternResult(
            pattern='Flat Base',
            detail=f'Range {flat_range*100:.1f}% over {n} bars',
        )

    # ── Double Bottom: two lows within 3% ─────────────────────────────────
    # Split into two halves and find minimum of each
    half = n // 2
    first_low = float(np.min(close[:half]))
    second_low = float(np.min(close[half:]))
    if abs(first_low - second_low) / max(first_low, second_low) <= 0.03:
        return BasePatternResult(
            pattern='Double Bottom',
            detail=f'Low1 {first_low:.2f} | Low2 {second_low:.2f}',
        )

    # ── Cup with Handle: drop >15%, recover near high, then small handle ──
    # Look for the low point somewhere in the first 2/3 of the window
    split = int(n * 0.67)
    cup_low = float(np.min(close[:split]))
    cup_high_before = float(np.max(close[:10]))  # starting high
    cup_high_after = float(np.max(close[split:]))

    drop_pct = (cup_high_before - cup_low) / cup_high_before
    recovery_pct = (cup_high_after - cup_low) / (cup_high_before - cup_low + 1e-9)

    # Handle = last 12% of the window should be tight (<12% range)
    handle_bars = max(5, int(n * 0.12))
    handle_close = close[-handle_bars:]
    handle_range = (np.max(handle_close) - np.min(handle_close)) / np.max(handle_close)

    if drop_pct >= 0.15 and recovery_pct >= 0.85 and handle_range <= 0.12:
        return BasePatternResult(
            pattern='Cup with Handle',
            detail=f'Drop {drop_pct*100:.1f}% | Recovery {recovery_pct*100:.0f}% | Handle {handle_range*100:.1f}%',
        )

    return BasePatternResult(pattern='None', detail='No recognisable base pattern')


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 – VCP Detection
# ─────────────────────────────────────────────────────────────────────────────

def analyze_vcp(df: pd.DataFrame) -> VCPResult:
    recent = df.tail(60).copy()
    n = len(recent)
    if n < 40:
        return VCPResult(rating='None', contracting_segments=0, volume_decreasing=False)

    high = recent['high'].values
    low = recent['low'].values
    vol = recent['volume'].values

    # Split into 4 roughly equal segments
    seg_size = n // 4
    segments = [
        slice(i * seg_size, (i + 1) * seg_size if i < 3 else n)
        for i in range(4)
    ]

    ranges: list[float] = []
    avg_vols: list[float] = []
    for s in segments:
        h = high[s]
        l = low[s]
        v = vol[s]
        mid = float(np.mean((h + l) / 2)) or 1.0
        ranges.append(float(np.max(h) - np.min(l)) / mid * 100.0)
        avg_vols.append(float(np.mean(v)))

    # Count contracting consecutive pairs
    contracting = sum(
        1 for i in range(len(ranges) - 1) if ranges[i] > ranges[i + 1]
    )
    volume_decreasing = all(
        avg_vols[i] > avg_vols[i + 1] for i in range(len(avg_vols) - 1)
    )

    # Last contraction should be <50% of first for a clean VCP
    tight_enough = ranges[-1] < ranges[0] * 0.5 if ranges[0] > 0 else False

    if contracting == 3 and volume_decreasing and tight_enough:
        rating = 'Excellent'
    elif contracting == 3 and volume_decreasing:
        rating = 'Good'
    elif contracting >= 2:
        rating = 'Good' if volume_decreasing else 'Weak'
    else:
        rating = 'None'

    return VCPResult(
        rating=rating,
        contracting_segments=contracting,
        volume_decreasing=volume_decreasing,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 – Tight Action (3-week range)
# ─────────────────────────────────────────────────────────────────────────────

def analyze_tight_action(df: pd.DataFrame) -> TightActionResult:
    recent = df.tail(15).copy()
    if len(recent) < 10:
        return TightActionResult(rating='Weak', avg_range_pct=float('nan'))

    weekly_ranges: list[float] = []
    # Split 15 bars into 3 x 5-bar pseudo-weeks
    for w in range(3):
        chunk = recent.iloc[w * 5:(w + 1) * 5]
        if chunk.empty:
            continue
        h = chunk['high'].max()
        l = chunk['low'].min()
        c = chunk['close'].iloc[-1]
        if c > 0:
            weekly_ranges.append((h - l) / c * 100.0)

    if not weekly_ranges:
        return TightActionResult(rating='Weak', avg_range_pct=float('nan'))

    avg_range = float(np.mean(weekly_ranges))

    if avg_range <= 5.0:
        rating = 'Excellent'
    elif avg_range <= 8.0:
        rating = 'Good'
    else:
        rating = 'Weak'

    return TightActionResult(rating=rating, avg_range_pct=avg_range)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 – Pocket Pivot
# ─────────────────────────────────────────────────────────────────────────────

def analyze_pocket_pivot(df: pd.DataFrame) -> PocketPivotResult:
    if len(df) < 25:
        return PocketPivotResult(found=False, date=None, volume_ratio=None)

    close = df['close'].values
    volume = df['volume'].values
    open_ = df['open'].values

    # Compute 10-day MA for close (used as proxy for MA10)
    ma10 = np.convolve(close, np.ones(10) / 10, mode='valid')
    # Pad left so indices align with close
    ma10_aligned = np.concatenate([np.full(9, np.nan), ma10])

    # Look for pocket pivot in last 5 trading days
    check_window = df.index[-5:]
    for idx_pos in range(len(df) - 5, len(df)):
        # Need at least 10 previous bars to evaluate down-day volume
        if idx_pos < 11:
            continue

        # Volume of down-days in the prior 10 bars
        prior_slice = slice(idx_pos - 10, idx_pos)
        prior_close = close[prior_slice]
        prior_open = open_[prior_slice]
        prior_vol = volume[prior_slice]

        down_day_vols = prior_vol[prior_close < prior_open]
        if len(down_day_vols) == 0:
            continue
        max_down_vol = float(np.max(down_day_vols))

        today_vol = volume[idx_pos]
        today_close = close[idx_pos]
        today_open = open_[idx_pos]
        today_ma10 = ma10_aligned[idx_pos]

        is_up_day = today_close > today_open
        above_ma = (not np.isnan(today_ma10)) and (today_close > today_ma10)
        volume_surge = today_vol > max_down_vol

        if is_up_day and above_ma and volume_surge and max_down_vol > 0:
            ratio = today_vol / max_down_vol
            date_str = str(df.index[idx_pos].date())
            return PocketPivotResult(found=True, date=date_str, volume_ratio=ratio)

    return PocketPivotResult(found=False, date=None, volume_ratio=None)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 – Breakout Analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze_breakout(df: pd.DataFrame) -> BreakoutResult:
    close = df['close'].values
    high = df['high'].values
    volume = df['volume'].values

    current_price = float(close[-1])
    latest_volume = float(volume[-1])

    # Pivot = max of last 60 bars high (base high) or 52wk high, whichever is lower
    # (We use the more conservative base high so distance is realistic)
    base_high = float(np.max(high[-60:])) if len(high) >= 60 else float(np.max(high))
    high_52wk = float(np.max(high[-252:])) if len(high) >= 252 else float(np.max(high))
    # Use the 60-bar high as pivot; 52wk high is additional context
    pivot_price = base_high

    avg_vol_20 = float(np.mean(volume[-20:])) if len(volume) >= 20 else float(np.mean(volume))
    breakout_volume_ratio = latest_volume / avg_vol_20 if avg_vol_20 > 0 else 1.0

    distance_pct = (current_price - pivot_price) / pivot_price * 100.0

    extended = distance_pct > 10.0

    if current_price >= pivot_price:
        # Already broken out
        if breakout_volume_ratio >= 2.0:
            rating = 'Excellent'
        elif breakout_volume_ratio >= 1.5:
            rating = 'Good'
        else:
            rating = 'Weak'
        action = 'BUY — Breakout in progress' if not extended else 'WAIT — Extended from pivot'
    else:
        rating = 'Not Yet'
        action = 'Wait For Breakout'

    if extended:
        action = 'WAIT — Extended (>{:.1f}%) from pivot'.format(distance_pct)

    return BreakoutResult(
        pivot_price=pivot_price,
        current_price=current_price,
        distance_pct=distance_pct,
        breakout_volume_ratio=breakout_volume_ratio,
        avg_vol_20=avg_vol_20,
        rating=rating,
        extended=extended,
        action=action,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11 – Position Sizing
# ─────────────────────────────────────────────────────────────────────────────

def calculate_position(
    current_price: float,
    pivot_price: float,
    portfolio_size: float = PORTFOLIO_SIZE,
    risk_percent: float = RISK_PERCENT,
) -> PositionResult:
    stop_pct = 0.07
    risk_amount = portfolio_size * risk_percent
    stop_loss = current_price * (1 - stop_pct)
    risk_per_share = current_price - stop_loss

    position_size = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

    entry_low = current_price
    entry_high = pivot_price * 1.02

    target1 = entry_low * 1.20
    target2 = entry_low * 1.40

    reward = target1 - entry_low
    risk = entry_low - stop_loss
    risk_reward = reward / risk if risk > 0 else 0.0

    return PositionResult(
        portfolio_size=portfolio_size,
        risk_amount=risk_amount,
        stop_loss=stop_loss,
        stop_pct=stop_pct,
        risk_per_share=risk_per_share,
        position_size=position_size,
        entry_low=entry_low,
        entry_high=entry_high,
        target1=target1,
        target2=target2,
        risk_reward=risk_reward,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(
    symbol: str,
    exchange: str,
    portfolio_size: float = PORTFOLIO_SIZE,
    risk_percent: float = RISK_PERCENT,
) -> SEPAResult:
    exchange = exchange.upper()
    symbol = symbol.upper()

    if exchange not in EXCHANGES:
        raise ValueError(
            f"Unknown exchange '{exchange}'. Supported: {list(EXCHANGES.keys())}"
        )

    cfg = EXCHANGES[exchange]

    # ── Fetch stock OHLCV ─────────────────────────────────────────────────
    stock_df = fetch_ohlcv(symbol, exchange, n_bars=300)
    current_price = float(stock_df['close'].iloc[-1])

    # ── Phase 1: Market ───────────────────────────────────────────────────
    market = analyze_market(cfg['index'], cfg['index_exchange'])

    # ── Fetch index OHLCV for RS calculation ─────────────────────────────
    try:
        index_df = fetch_ohlcv(cfg['index'], cfg['index_exchange'], n_bars=300)
    except RuntimeError:
        # Construct flat index as fallback so RS returns ~50
        index_df = stock_df.copy()
        index_df['close'] = 100.0

    # ── Phase 2: Trend Template ───────────────────────────────────────────
    trend = analyze_trend(stock_df)

    # ── Phase 3: Relative Strength ────────────────────────────────────────
    rs = analyze_rs(stock_df, index_df)

    # ── Fetch fundamentals ────────────────────────────────────────────────
    fund_data = fetch_fundamentals(symbol, cfg['yf_suffix'])

    # ── Phase 4: Fundamentals ─────────────────────────────────────────────
    fundamental = analyze_fundamentals(fund_data)

    # ── Phase 5: Institutional ────────────────────────────────────────────
    institutional = analyze_institutional(fund_data)

    # ── Phase 6: Base Pattern ─────────────────────────────────────────────
    base_pattern = analyze_base_pattern(stock_df)

    # ── Phase 7: VCP ──────────────────────────────────────────────────────
    vcp = analyze_vcp(stock_df)

    # ── Phase 8: Tight Action ─────────────────────────────────────────────
    tight_action = analyze_tight_action(stock_df)

    # ── Phase 9: Pocket Pivot ─────────────────────────────────────────────
    pocket_pivot = analyze_pocket_pivot(stock_df)

    # ── Phase 10: Breakout ────────────────────────────────────────────────
    breakout = analyze_breakout(stock_df)

    # ── Phase 11: Position Sizing ─────────────────────────────────────────
    position = calculate_position(
        current_price=current_price,
        pivot_price=breakout.pivot_price,
        portfolio_size=portfolio_size,
        risk_percent=risk_percent,
    )

    return SEPAResult(
        symbol=symbol,
        exchange=exchange,
        current_price=current_price,
        market=market,
        trend=trend,
        rs=rs,
        fundamental=fundamental,
        institutional=institutional,
        base_pattern=base_pattern,
        vcp=vcp,
        tight_action=tight_action,
        pocket_pivot=pocket_pivot,
        breakout=breakout,
        position=position,
    )
