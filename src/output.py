from __future__ import annotations

from .analyzer import SEPAResult
from .scoring import ScoreBreakdown, build_key_reasons, build_risk_factors, build_action

_W = 51  # total width of the box


def _header(title: str) -> str:
    return '\n' + '═' * _W + f'\n{title}\n' + '═' * _W


def _section(title: str) -> str:
    return f'\n{title}\n' + '─' * _W


def _row(label: str, value: str, width: int = 20) -> str:
    return f"{label:<{width}}: {value}"


def _fmt_price(price: float, prefix: str = '$') -> str:
    if price != price:  # NaN check
        return 'N/A'
    return f'{prefix}{price:,.2f}'


def _fmt_pct(pct: float, sign: bool = False) -> str:
    if pct != pct:
        return 'N/A'
    if sign:
        return f'{pct:+.1f}%'
    return f'{pct:.1f}%'


def _distance_label(distance_pct: float) -> str:
    if distance_pct < 0:
        return f'{distance_pct:.1f}% [Below Pivot]'
    if distance_pct <= 5:
        return f'+{distance_pct:.1f}% [Excellent]'
    if distance_pct <= 10:
        return f'+{distance_pct:.1f}% [Acceptable]'
    return f'+{distance_pct:.1f}% [Extended]'


def format_output(result: SEPAResult, score: ScoreBreakdown) -> str:
    sym = result.symbol
    exch = result.exchange
    pos = result.position
    bo = result.breakout
    fund = result.fundamental

    # Determine currency symbol
    currency = '$' if exch in ('NASDAQ', 'NYSE') else '฿'

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────
    lines.append(_header(f'SEPA ANALYSIS — {sym} ({exch})'))

    # ── Market & Trend ────────────────────────────────────────────────────
    lines.append(_section('MARKET & TREND'))
    lines.append(_row('Market Condition', result.market.condition))
    trend_str = f'{result.trend.conditions_met}/{result.trend.total}'
    if not result.trend.passed:
        trend_str += ' [Below Threshold]'
    lines.append(_row('Trend Template', trend_str))
    lines.append(_row('Relative Strength', f'{result.rs.rating} (RS: {result.rs.rs_avg:.0f})'))

    # ── Fundamental ───────────────────────────────────────────────────────
    lines.append(_section('FUNDAMENTAL'))

    if fund.available:
        eps_str = (
            f'{_fmt_pct(fund.eps_growth_pct, sign=True)} [{fund.eps_rating}]'
            if fund.eps_growth_pct is not None
            else f'N/A [{fund.eps_rating}]'
        )
        lines.append(_row('EPS Growth', eps_str))

        rev_str = (
            f'{_fmt_pct(fund.revenue_growth_pct, sign=True)} [{fund.revenue_rating}]'
            if fund.revenue_growth_pct is not None
            else f'N/A [{fund.revenue_rating}]'
        )
        lines.append(_row('Revenue Growth', rev_str))

        ann_str = (
            f'{_fmt_pct(fund.annual_eps_growth_pct, sign=True)} [{fund.annual_eps_rating}]'
            if fund.annual_eps_growth_pct is not None
            else f'N/A [{fund.annual_eps_rating}]'
        )
        lines.append(_row('Annual EPS Growth', ann_str))

        roe_str = (
            f'{_fmt_pct(fund.roe_pct)} [{fund.roe_rating}]'
            if fund.roe_pct is not None
            else f'N/A [{fund.roe_rating}]'
        )
        lines.append(_row('ROE', roe_str))
        lines.append(_row('Margin Trend', fund.margin_trend))
    else:
        lines.append(_row('Fundamentals', 'N/A (data unavailable)'))

    lines.append(_row('Institutional', result.institutional.rating + (
        f' ({result.institutional.pct_held:.1f}% held)'
        if result.institutional.pct_held is not None else ''
    )))

    # ── Technical Pattern ─────────────────────────────────────────────────
    lines.append(_section('TECHNICAL PATTERN'))
    lines.append(_row('Base Pattern', result.base_pattern.pattern))
    lines.append(_row('VCP', result.vcp.rating))
    tight_str = f'{result.tight_action.rating}'
    if result.tight_action.avg_range_pct == result.tight_action.avg_range_pct:  # not NaN
        tight_str += f' (range {result.tight_action.avg_range_pct:.1f}%)'
    lines.append(_row('Tight Action', tight_str))
    pp_str = 'Found' if result.pocket_pivot.found else 'Not Found'
    if result.pocket_pivot.found and result.pocket_pivot.date:
        pp_str += f' ({result.pocket_pivot.date})'
    lines.append(_row('Pocket Pivot', pp_str))

    # ── Entry & Risk ──────────────────────────────────────────────────────
    lines.append(_section('ENTRY & RISK'))
    lines.append(_row('Current Price', _fmt_price(result.current_price, currency)))
    lines.append(_row('Pivot Price', _fmt_price(bo.pivot_price, currency)))
    lines.append(_row('Distance From Pivot', _distance_label(bo.distance_pct)))
    entry_zone = f'{_fmt_price(pos.entry_low, currency)} — {_fmt_price(pos.entry_high, currency)}'
    lines.append(_row('Entry Zone', entry_zone))
    lines.append(_row('Stop Loss', f'{_fmt_price(pos.stop_loss, currency)} (-{pos.stop_pct*100:.0f}%)'))
    lines.append(_row('Target 1', f'{_fmt_price(pos.target1, currency)} (+20%)'))
    lines.append(_row('Target 2', f'{_fmt_price(pos.target2, currency)} (+40%)'))
    lines.append(_row('Risk/Reward', f'1:{pos.risk_reward:.1f}'))
    lines.append(_row('Position Size', f'{pos.position_size:,} Shares'))

    # ── Score & Recommendation ────────────────────────────────────────────
    lines.append('\n' + '═' * _W)
    bear_note = ' (bear-market adjusted)' if score.bear_adjusted else ''
    lines.append(f"{'CONFIDENCE SCORE':<20}: {score.final:.0f}/100{bear_note}")
    lines.append(f"{'RECOMMENDATION':<20}: {score.recommendation}")
    lines.append('═' * _W)

    # ── Key Reasons ───────────────────────────────────────────────────────
    key_reasons = build_key_reasons(result, score)
    risk_factors = build_risk_factors(result, score)
    action = build_action(result, score)

    lines.append('\nKEY REASONS')
    if key_reasons:
        for i, r in enumerate(key_reasons, 1):
            lines.append(f'{i}. {r}')
    else:
        lines.append('1. Insufficient data to generate key reasons')

    lines.append('\nRISK FACTORS')
    if risk_factors:
        for i, r in enumerate(risk_factors, 1):
            lines.append(f'{i}. {r}')
    else:
        lines.append('1. No major risk factors identified')

    # ── Action Plan ───────────────────────────────────────────────────────
    lines.append(_section('ACTION PLAN'))
    lines.append(f'► {action}')

    # ── Pyramid Strategy ──────────────────────────────────────────────────
    if score.recommendation in ('Strong Buy', 'Buy', 'Watchlist'):
        lines.append('\nPYRAMID STRATEGY (if entering)')
        p1_shares = pos.position_size
        p2_shares = int(p1_shares * 0.5)
        p3_shares = int(p1_shares * 0.25)

        p1_price = pos.entry_low
        p2_price = pos.entry_low * 1.025   # +2.5%
        p3_price = pos.entry_low * 1.06    # +6%

        lines.append(
            f'Position 1: {p1_shares:>6,} shares @ {_fmt_price(p1_price, currency)} (Breakout)'
        )
        lines.append(
            f'Position 2: {p2_shares:>6,} shares @ {_fmt_price(p2_price, currency)} (+2-3%)'
        )
        lines.append(
            f'Position 3: {p3_shares:>6,} shares @ {_fmt_price(p3_price, currency)} (+5-7%)'
        )

    lines.append('═' * _W)

    return '\n'.join(lines)


def print_output(result: SEPAResult, score: ScoreBreakdown) -> None:
    print(format_output(result, score))
