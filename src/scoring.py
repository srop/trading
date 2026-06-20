from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .analyzer import SEPAResult


@dataclass
class ScoreBreakdown:
    market: float
    trend: float
    rs: float
    fundamental: float
    institutional: float
    base_pattern: float
    vcp: float
    pocket_pivot: float
    volume: float
    final: float
    recommendation: str
    bear_adjusted: bool


WEIGHTS: dict[str, float] = {
    'market':       0.10,
    'trend':        0.20,
    'rs':           0.20,
    'fundamental':  0.20,
    'institutional':0.10,
    'base_pattern': 0.05,
    'vcp':          0.05,
    'pocket_pivot': 0.05,
    'volume':       0.05,
}


def _market_score(condition: str) -> float:
    return {'Bullish': 100.0, 'Neutral': 50.0, 'Bearish': 0.0}.get(condition, 50.0)


def _trend_score(result) -> float:
    # Reject (0) if < 7/9; otherwise proportional
    if not result.passed:
        return 0.0
    return (result.conditions_met / result.total) * 100.0


def _rs_score(rating: str) -> float:
    return {'Leader': 100.0, 'Strong': 80.0, 'Average': 50.0, 'Weak': 0.0}.get(rating, 50.0)


def _sub_fundamental(rating: str) -> float:
    return {'Excellent': 100.0, 'Strong': 70.0, 'Weak': 30.0, 'N/A': 50.0}.get(rating, 50.0)


def _fundamental_score(result) -> float:
    if not result.available:
        return 50.0  # neutral when no data

    subs = [
        _sub_fundamental(result.eps_rating),
        _sub_fundamental(result.revenue_rating),
        _sub_fundamental(result.roe_rating),
        _sub_fundamental(result.annual_eps_rating),
    ]
    return float(sum(subs) / len(subs))


def _institutional_score(rating: str) -> float:
    return {'Positive': 100.0, 'Neutral': 50.0, 'Negative': 0.0}.get(rating, 50.0)


def _base_pattern_score(pattern: str) -> float:
    return {
        'Cup with Handle': 100.0,
        'Flat Base':        90.0,
        'Double Bottom':    80.0,
        'None':              0.0,
    }.get(pattern, 0.0)


def _vcp_score(rating: str) -> float:
    return {'Excellent': 100.0, 'Good': 70.0, 'Weak': 40.0, 'None': 0.0}.get(rating, 0.0)


def _pocket_pivot_score(found: bool) -> float:
    return 100.0 if found else 0.0


def _volume_score(rating: str) -> float:
    # Reuse breakout rating as volume proxy
    return {'Excellent': 100.0, 'Good': 70.0, 'Weak': 30.0, 'Not Yet': 30.0}.get(rating, 30.0)


def _recommendation(score: float) -> str:
    if score >= 85:
        return 'Strong Buy'
    if score >= 75:
        return 'Buy'
    if score >= 60:
        return 'Watchlist'
    if score >= 40:
        return 'Avoid'
    return 'Reject'


def calculate_score(result: SEPAResult) -> ScoreBreakdown:
    scores = {
        'market':       _market_score(result.market.condition),
        'trend':        _trend_score(result.trend),
        'rs':           _rs_score(result.rs.rating),
        'fundamental':  _fundamental_score(result.fundamental),
        'institutional':_institutional_score(result.institutional.rating),
        'base_pattern': _base_pattern_score(result.base_pattern.pattern),
        'vcp':          _vcp_score(result.vcp.rating),
        'pocket_pivot': _pocket_pivot_score(result.pocket_pivot.found),
        'volume':       _volume_score(result.breakout.rating),
    }

    final = sum(WEIGHTS[k] * v for k, v in scores.items())

    bear_adjusted = False
    if result.market.is_bear:
        final *= 0.75
        bear_adjusted = True

    # Clamp extended positions — reduce score if way past pivot
    if result.breakout.extended:
        final *= 0.85

    final = round(min(100.0, max(0.0, final)), 1)

    return ScoreBreakdown(
        market=round(scores['market'], 1),
        trend=round(scores['trend'], 1),
        rs=round(scores['rs'], 1),
        fundamental=round(scores['fundamental'], 1),
        institutional=round(scores['institutional'], 1),
        base_pattern=round(scores['base_pattern'], 1),
        vcp=round(scores['vcp'], 1),
        pocket_pivot=round(scores['pocket_pivot'], 1),
        volume=round(scores['volume'], 1),
        final=final,
        recommendation=_recommendation(final),
        bear_adjusted=bear_adjusted,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Key Reasons & Risk Factors (narrative generation)
# ─────────────────────────────────────────────────────────────────────────────

def build_key_reasons(result: SEPAResult, score: ScoreBreakdown) -> list[str]:
    reasons: list[str] = []

    if result.market.condition == 'Bullish':
        reasons.append(f"Market is Bullish — index above both MA50 and MA200")

    if result.trend.passed:
        reasons.append(
            f"Trend Template passed {result.trend.conditions_met}/9 conditions (minimum 7 required)"
        )

    if result.rs.rating in ('Leader', 'Strong'):
        reasons.append(
            f"Relative Strength is {result.rs.rating} (RS: {result.rs.rs_avg:.0f}) — outperforming the index"
        )

    if result.fundamental.available:
        if result.fundamental.eps_rating == 'Excellent':
            reasons.append(
                f"EPS Growth +{result.fundamental.eps_growth_pct:.0f}% YoY — Excellent earnings acceleration"
            )
        if result.fundamental.revenue_rating == 'Excellent':
            reasons.append(
                f"Revenue Growth +{result.fundamental.revenue_growth_pct:.0f}% — Excellent top-line expansion"
            )
        if result.fundamental.roe_rating == 'Excellent':
            reasons.append(
                f"ROE {result.fundamental.roe_pct:.1f}% — Excellent capital efficiency"
            )

    if result.vcp.rating in ('Excellent', 'Good'):
        reasons.append(
            f"VCP pattern detected ({result.vcp.rating}) with {result.vcp.contracting_segments} contracting segments"
        )

    if result.base_pattern.pattern != 'None':
        reasons.append(f"Base pattern: {result.base_pattern.pattern} — {result.base_pattern.detail}")

    if result.pocket_pivot.found:
        reasons.append(
            f"Pocket Pivot detected on {result.pocket_pivot.date} "
            f"(vol ×{result.pocket_pivot.volume_ratio:.1f} vs down-day max)"
        )

    if result.tight_action.rating == 'Excellent':
        reasons.append(
            f"Tight price action — 3-week range only {result.tight_action.avg_range_pct:.1f}%"
        )

    # Keep top 5
    return reasons[:5]


def build_risk_factors(result: SEPAResult, score: ScoreBreakdown) -> list[str]:
    risks: list[str] = []

    if result.market.is_bear:
        risks.append("Bear market environment — score reduced 25%; use smaller position sizes")

    if result.market.condition == 'Neutral':
        risks.append("Mixed market conditions — index not in clear uptrend")

    if not result.trend.passed:
        risks.append(
            f"Trend Template only {result.trend.conditions_met}/9 — stock is not in a Stage 2 uptrend"
        )

    if result.rs.rating in ('Weak', 'Average'):
        risks.append(f"Relative Strength is {result.rs.rating} — underperforming the market")

    if result.breakout.extended:
        risks.append(
            f"Price is {result.breakout.distance_pct:.1f}% past the pivot — extended, higher failure risk"
        )

    if result.vcp.rating in ('Weak', 'None'):
        risks.append("No clear VCP pattern — consolidation may not be constructive")

    if result.fundamental.available:
        if result.fundamental.eps_rating == 'Weak':
            risks.append("Weak EPS growth — earnings momentum not meeting SEPA standards")
        if result.fundamental.revenue_rating == 'Weak':
            risks.append("Weak revenue growth — top-line acceleration is lacking")
    else:
        risks.append("Fundamental data unavailable from yfinance — manual verification required")

    if result.institutional.rating == 'Negative':
        risks.append("Low institutional ownership — lack of big-money sponsorship")

    # Keep top 3
    return risks[:3]


def build_action(result: SEPAResult, score: ScoreBreakdown) -> str:
    if score.recommendation in ('Reject', 'Avoid'):
        return 'Avoid — Does not meet SEPA criteria'

    if result.market.is_bear:
        return 'WAIT — Bear market; hold cash until market improves'

    if result.breakout.extended:
        return f'WAIT — Extended {result.breakout.distance_pct:.1f}% past pivot; wait for pullback to MA10/MA21'

    if result.breakout.rating == 'Not Yet':
        return f'Wait For Breakout above ${result.breakout.pivot_price:.2f} on volume ≥1.5× average'

    if score.recommendation == 'Strong Buy':
        return f'BUY NOW — All systems go; enter at market or on intraday pullback'

    if score.recommendation == 'Buy':
        return 'BUY — Good setup; consider a starter position and add on confirmation'

    return 'Watchlist — Monitor daily; enter on volume breakout or pocket pivot'
