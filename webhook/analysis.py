"""Run full SEPA analysis + OpenRouter AI summary for a breakout alert."""
from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # add project root

from dataclasses import dataclass

from openai import OpenAI
from src.analyzer import run_analysis, SEPAResult
from src.scoring import (
    calculate_score,
    ScoreBreakdown,
    build_key_reasons,
    build_risk_factors,
    build_action,
)
from src.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, EXCHANGES


@dataclass
class FullScoreResult:
    """ScoreBreakdown extended with narrative fields used by format_alert()."""
    # Delegate numeric fields from ScoreBreakdown
    confidence_score: float
    recommendation: str
    bear_adjusted: bool
    # Breakdown sub-scores
    market: float
    trend: float
    rs: float
    fundamental: float
    institutional: float
    base_pattern: float
    vcp: float
    pocket_pivot: float
    volume: float
    # Narrative fields
    key_reasons: list[str]
    risk_factors: list[str]
    action_plan: str

    @classmethod
    def from_score(cls, score: ScoreBreakdown, result: SEPAResult) -> "FullScoreResult":
        return cls(
            confidence_score=score.final,
            recommendation=score.recommendation,
            bear_adjusted=score.bear_adjusted,
            market=score.market,
            trend=score.trend,
            rs=score.rs,
            fundamental=score.fundamental,
            institutional=score.institutional,
            base_pattern=score.base_pattern,
            vcp=score.vcp,
            pocket_pivot=score.pocket_pivot,
            volume=score.volume,
            key_reasons=build_key_reasons(result, score),
            risk_factors=build_risk_factors(result, score),
            action_plan=build_action(result, score),
        )


def run_breakout_analysis(
    ticker: str,
    exchange: str,
    webhook_data: dict,
) -> tuple[SEPAResult, FullScoreResult, str]:
    """
    Returns (SEPAResult, FullScoreResult, ai_summary_str).
    webhook_data: parsed JSON from TradingView alert.
    """
    result = run_analysis(ticker, exchange)
    score  = calculate_score(result)
    scored = FullScoreResult.from_score(score, result)
    ai_summary = _get_ai_summary(result, scored, webhook_data)
    return result, scored, ai_summary


def _get_ai_summary(
    result: SEPAResult,
    scored: FullScoreResult,
    webhook_data: dict,
) -> str:
    """Call OpenRouter for a short qualitative SEPA summary (<=5 bullets)."""
    if not OPENROUTER_API_KEY:
        return "AI summary unavailable — OPENROUTER_API_KEY not set"

    eps_growth = result.fundamental.eps_growth_pct
    rev_growth = result.fundamental.revenue_growth_pct
    roe        = result.fundamental.roe_pct

    prompt = f"""หุ้น {result.symbol} ({result.exchange}) เพิ่งเกิด breakout ตามสัญญาณ SEPA

ข้อมูลเชิงปริมาณ:
- Trend Template: {result.trend.conditions_met}/9
- RS Rating: {result.rs.rating}
- EPS Growth: {f'{eps_growth:+.1f}%' if eps_growth is not None else 'N/A'}
- Revenue Growth: {f'{rev_growth:+.1f}%' if rev_growth is not None else 'N/A'}
- ROE: {f'{roe:.1f}%' if roe is not None else 'N/A'}
- Base Pattern: {result.base_pattern.pattern}
- VCP: {result.vcp.rating}
- Pocket Pivot: {result.pocket_pivot.found}
- Breakout Volume: {webhook_data.get('vol_ratio', '?')}x ค่าเฉลี่ย
- ห่างจาก Pivot: {result.breakout.distance_pct:+.1f}%
- คะแนน: {scored.confidence_score:.0f}/100
- คำแนะนำ: {scored.recommendation}

สรุปเป็นภาษาไทยในรูปแบบประโยคสั้นๆ ติดต่อกัน ไม่เกิน 200 ตัวอักษร
ใช้ภาษาที่คนทั่วไปเข้าใจได้ ไม่ใช้ศัพท์เทคนิค
บอกให้ชัดว่าหุ้นนี้น่าสนใจแค่ไหน เหตุผลหลักคืออะไร และความเสี่ยงที่ต้องระวัง"""

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        extra_headers={
            "HTTP-Referer": "https://github.com/tradebot",
            "X-Title": "SEPA Webhook",
        },
    )
    return resp.choices[0].message.content.strip()
