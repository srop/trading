"""Check exit conditions for open positions (Minervini-style)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

logging.getLogger('tvDatafeed').setLevel(logging.ERROR)

from tvDatafeed import Interval, TvDatafeed

if TYPE_CHECKING:
    from src.sheets import Position

logger = logging.getLogger(__name__)

_tv = TvDatafeed()


@dataclass
class ExitSignal:
    position: object      # Position from sheets.py
    current_price: float
    reason: str           # "Stop Loss" | "Target 1 Reached" | "Target 2 Reached" | "Trend Break (below MA50)"
    action: str           # "SELL NOW" | "SELL HALF"
    pnl_pct: float


def get_current_price(symbol: str, exchange: str) -> Optional[float]:
    """Fetch the latest 15-minute close price from TradingView."""
    try:
        df = _tv.get_hist(symbol, exchange, Interval.in_15_minute, n_bars=5)
        if df is not None and len(df) > 0:
            return float(df['close'].iloc[-1])
    except Exception as e:
        logger.debug(f"get_current_price failed for {symbol}: {e}")
    return None


def check_exit(position: object) -> Optional[ExitSignal]:
    """
    Evaluate exit conditions for a single open position.
    Returns ExitSignal if an exit is warranted, else None.
    """
    price = get_current_price(position.symbol, position.exchange)
    if not price:
        return None

    pnl_pct = (price - position.entry_price) / position.entry_price * 100

    # Stop Loss — exit immediately
    if price <= position.stop_loss:
        return ExitSignal(
            position=position,
            current_price=price,
            reason='ตัดขาดทุน (Stop Loss)',
            action='ขายทันที',
            pnl_pct=pnl_pct,
        )

    # Target 2 — full exit
    if price >= position.target2:
        return ExitSignal(
            position=position,
            current_price=price,
            reason='ถึงเป้าที่ 2 (+40%)',
            action='ขายทั้งหมด',
            pnl_pct=pnl_pct,
        )

    # Target 1 — sell half
    if price >= position.target1:
        return ExitSignal(
            position=position,
            current_price=price,
            reason='ถึงเป้าที่ 1 (+20%)',
            action='ขายครึ่ง',
            pnl_pct=pnl_pct,
        )

    # Trend Break: price < MA50 (daily data)
    try:
        df = _tv.get_hist(
            position.symbol, position.exchange, Interval.in_daily, n_bars=60
        )
        if df is not None and len(df) >= 50:
            ma50 = df['close'].rolling(50).mean().iloc[-1]
            if price < ma50:
                return ExitSignal(
                    position=position,
                    current_price=price,
                    reason='Trend แตก (ต่ำกว่า MA50)',
                    action='ขายทันที',
                    pnl_pct=pnl_pct,
                )
    except Exception as e:
        logger.debug(f"MA50 check failed for {position.symbol}: {e}")

    return None


def format_exit_alert(signal: ExitSignal) -> str:
    """Format an exit signal into a Telegram HTML message."""
    pos = signal.position
    currency = '฿' if pos.exchange == 'SET' else '$'

    pnl_emoji = '🟢' if signal.pnl_pct >= 0 else '🔴'

    if signal.action == 'SELL NOW':
        action_text = '🔴 SELL NOW'
    else:
        action_text = '🟡 SELL HALF'

    # Dollar PnL (approximate: shares × price change)
    price_diff = signal.current_price - pos.entry_price
    dollar_pnl = price_diff * pos.shares

    return (
        f"🔔 <b>EXIT SIGNAL — {pos.symbol} ({pos.exchange})</b>\n"
        f"{'─' * 33}\n"
        f"Reason   : {signal.reason}\n"
        f"Action   : {action_text}\n\n"
        f"Entry    : {currency}{pos.entry_price:,.2f} ({pos.entry_date})\n"
        f"Current  : {currency}{signal.current_price:,.2f}\n"
        f"PnL      : {pnl_emoji} {signal.pnl_pct:+.1f}% | {pnl_emoji} {dollar_pnl:+,.0f} {currency.replace('$','USD').replace('฿','THB')}\n\n"
        f"Shares   : {pos.shares:,}\n"
        f"Stop     : {currency}{pos.stop_loss:,.2f}\n"
        f"{'─' * 33}\n"
        f"⚡ ดำเนินการทันที"
    )
