"""
Sends Top-N screened stocks to OpenRouter for qualitative SEPA analysis.
Uses the OpenAI-compatible SDK pointed at OpenRouter's API endpoint.
"""
from __future__ import annotations

from openai import OpenAI
from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from .screener import ScreenResult


def build_prompt(stocks: list[ScreenResult]) -> str:
    """Build SEPA analysis prompt from screened stock data."""

    stocks_text = ""
    for i, s in enumerate(stocks, 1):
        cond_str = "".join("Y" if c else "N" for c in s.conditions)
        stocks_text += (
            f"\n{i:2}. {s.symbol} ({s.exchange}) — {s.sector}\n"
            f"    Trend Template : {s.trend_score}/9  [{cond_str}]\n"
            f"    RS             : {s.rs_value} ({s.rs_rating})\n"
            f"    Price          : {s.current_price}\n"
            f"    Distance 52wkH : {s.distance_from_high:+.1f}%\n"
            f"    Volume Ratio   : {s.volume_ratio:.1f}x avg\n"
            f"    MA50/150/200   : {s.ma50} / {s.ma150} / {s.ma200}\n"
        )

    return f"""You are Mark Minervini's SEPA analyst. These {len(stocks)} stocks passed the Trend Template screen (>=8/9 conditions).

SCREENED STOCKS:
{stocks_text}

Analyze these stocks using Mark Minervini's SEPA framework and provide:

1. **PRIORITY RANKING** - Rank all {len(stocks)} stocks from strongest to weakest SEPA setup. For each: score rationale in 1 sentence.

2. **TOP 5 IMMEDIATE SETUPS** - Which 5 stocks have the best risk/reward RIGHT NOW? For each:
   - Why it's a top setup
   - Entry trigger to watch
   - Key risk

3. **SECTOR ANALYSIS** - Which sectors show the most strength? Any sector rotation signal?

4. **MARKET INTERNALS** - Based on this breadth of stocks passing the screen, what does it suggest about overall market health?

5. **AVOID LIST** - Which stocks on this list should still be avoided despite passing the screen? Why?

Be specific. No generic advice. Use Minervini's language (VCP, tight action, institutional accumulation, etc.)."""


def analyze_with_ai(stocks: list[ScreenResult]) -> str:
    """Send screened stocks to OpenRouter for SEPA analysis."""

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )

    prompt = build_prompt(stocks)

    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        extra_headers={
            "HTTP-Referer": "https://github.com/tradebot",
            "X-Title": "SEPA Screener",
        },
    )

    return response.choices[0].message.content
