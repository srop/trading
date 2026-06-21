"""
Telegram Bot — รับคำสั่งซื้อและแสดง portfolio
Run: python bot.py
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

from src.sheets import add_position, get_open_positions
from src.breakout import build_daily_cache
from src.exit_monitor import get_current_price

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)
logging.getLogger('tvDatafeed').setLevel(logging.ERROR)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = int(os.getenv('TELEGRAM_CHAT_ID', '0'))


def _is_authorized(update: Update) -> bool:
    """Return True only if the message comes from the configured chat."""
    return update.effective_chat is not None and update.effective_chat.id == CHAT_ID


# ─────────────────────────────────────────────────────────────────────────────
# /buy SYMBOL EXCHANGE PRICE SHARES
# ─────────────────────────────────────────────────────────────────────────────

async def buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Record a new position. Usage: /buy SYMBOL EXCHANGE PRICE SHARES"""
    if not _is_authorized(update):
        return

    args = context.args or []
    if len(args) != 4:
        await update.message.reply_text(
            "⚠️ รูปแบบไม่ถูกต้อง\n"
            "การใช้งาน: <code>/buy SYMBOL EXCHANGE PRICE SHARES</code>\n"
            "ตัวอย่าง: <code>/buy NVDA NASDAQ 210.50 678</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    symbol_raw, exchange_raw, price_raw, shares_raw = args

    # Validate numeric args
    try:
        entry_price = float(price_raw)
        shares = int(shares_raw)
    except ValueError:
        await update.message.reply_text(
            "⚠️ PRICE ต้องเป็นตัวเลข และ SHARES ต้องเป็นจำนวนเต็ม\n"
            "ตัวอย่าง: <code>/buy NVDA NASDAQ 210.50 678</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    symbol   = symbol_raw.upper()
    exchange = exchange_raw.upper()

    # Try to derive stop/targets from SEPA analysis
    stop_loss = target1 = target2 = None
    try:
        from src.analyzer import run_analysis
        result = run_analysis(symbol, exchange)
        stop_loss = result.position.stop_loss
        target1   = result.position.target1
        target2   = result.position.target2
        logger.info(f"SEPA data fetched for {symbol}: stop={stop_loss:.2f} t1={target1:.2f} t2={target2:.2f}")
    except Exception as e:
        logger.warning(f"SEPA analysis failed for {symbol}: {e} — using defaults")

    # Defaults if analysis failed
    if stop_loss is None:
        stop_loss = entry_price * 0.93
    if target1 is None:
        target1 = entry_price * 1.20
    if target2 is None:
        target2 = entry_price * 1.40

    # Save to sheet
    try:
        pos = add_position(
            symbol=symbol,
            exchange=exchange,
            entry_price=entry_price,
            shares=shares,
            stop_loss=stop_loss,
            target1=target1,
            target2=target2,
        )
    except Exception as e:
        logger.error(f"Failed to save position {symbol}: {e}")
        await update.message.reply_text(
            f"❌ บันทึกไม่สำเร็จ: <code>{str(e)[:200]}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    currency  = '฿' if exchange == 'SET' else '$'
    stop_pct  = (stop_loss  - entry_price) / entry_price * 100
    t1_pct    = (target1    - entry_price) / entry_price * 100
    t2_pct    = (target2    - entry_price) / entry_price * 100

    msg = (
        f"✅ <b>บันทึกแล้ว — {symbol} ({exchange})</b>\n\n"
        f"Entry       : {currency}{entry_price:,.2f}\n"
        f"Shares      : {shares:,}\n"
        f"Entry Date  : {pos.entry_date}\n\n"
        f"Stop Loss   : {currency}{stop_loss:,.2f} ({stop_pct:+.1f}%)\n"
        f"Target 1    : {currency}{target1:,.2f} ({t1_pct:+.1f}%) → Sell Half\n"
        f"Target 2    : {currency}{target2:,.2f} ({t2_pct:+.1f}%) → Sell All\n\n"
        f"จะแจ้งเตือนทาง Telegram เมื่อถึงจุดขาย 🔔"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────────────────────────────────────
# /positions
# ─────────────────────────────────────────────────────────────────────────────

async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display all open positions."""
    if not _is_authorized(update):
        return

    try:
        positions = get_open_positions()
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        await update.message.reply_text(
            f"❌ ดึงข้อมูลไม่สำเร็จ: <code>{str(e)[:200]}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    if not positions:
        await update.message.reply_text("ไม่มี open positions")
        return

    lines = [f"📋 <b>Open Positions ({len(positions)})</b>\n"]
    for i, pos in enumerate(positions, start=1):
        currency = '฿' if pos.exchange == 'SET' else '$'
        lines.append(
            f"{i}. <b>{pos.symbol} ({pos.exchange})</b>\n"
            f"   Entry: {currency}{pos.entry_price:,.2f} | {pos.shares:,} shares\n"
            f"   Stop: {currency}{pos.stop_loss:,.2f} | "
            f"T1: {currency}{pos.target1:,.2f} | "
            f"T2: {currency}{pos.target2:,.2f}\n"
            f"   Date: {pos.entry_date}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────────────────────────────────────

async def price_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current price + trend for a symbol. Usage: /price SYMBOL EXCHANGE"""
    if not _is_authorized(update):
        return

    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ การใช้งาน: <code>/price SYMBOL EXCHANGE</code>\n"
            "ตัวอย่าง: <code>/price GLD AMEX</code>  หรือ  <code>/price NVDA NASDAQ</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    symbol   = args[0].upper()
    exchange = args[1].upper()
    currency = '฿' if exchange == 'SET' else '$'

    await update.message.reply_text(f"⏳ กำลังดึงข้อมูล {symbol}...")

    price = get_current_price(symbol, exchange)
    if not price:
        await update.message.reply_text(f"❌ ดึงราคา {symbol} ไม่ได้ ลองใหม่อีกครั้ง")
        return

    cache = build_daily_cache(symbol, exchange)
    if not cache:
        await update.message.reply_text(
            f"💰 <b>{symbol} ({exchange})</b>\n"
            f"ราคาปัจจุบัน: <b>{currency}{price:,.2f}</b>\n"
            f"(ข้อมูล trend ไม่เพียงพอ)",
            parse_mode=ParseMode.HTML,
        )
        return

    # Trend direction
    if cache.trend_score >= 7:
        trend_label = "📈 ขาขึ้นแข็งแกร่ง"
    elif cache.trend_score >= 5:
        trend_label = "➡️ ทรงตัว / ไม่ชัดเจน"
    else:
        trend_label = "📉 ขาลง"

    # Position vs MAs
    vs_ma50  = (price / cache.ma50  - 1) * 100
    vs_ma150 = (price / cache.ma150 - 1) * 100
    vs_ma200 = (price / cache.ma200 - 1) * 100

    # Distance from 52w high/low
    from52h = (price / cache.high52w - 1) * 100
    from52l = (price / cache.low52w  - 1) * 100

    # Breakout zone check
    if price > cache.pivot:
        pivot_status = f"✅ เหนือ Pivot ({currency}{cache.pivot:,.2f})"
    else:
        gap = (cache.pivot / price - 1) * 100
        pivot_status = f"⏳ ห่างจาก Pivot {gap:.1f}% ({currency}{cache.pivot:,.2f})"

    msg = (
        f"🔍 <b>{symbol} ({exchange})</b>\n"
        f"{'─' * 30}\n"
        f"💰 ราคา: <b>{currency}{price:,.2f}</b>\n\n"
        f"<b>แนวโน้ม</b>\n"
        f"  {trend_label}  ({cache.trend_score}/9)\n"
        f"  {pivot_status}\n\n"
        f"<b>เทียบเส้นค่าเฉลี่ย</b>\n"
        f"  MA50  : {currency}{cache.ma50:,.2f}  ({vs_ma50:+.1f}%)\n"
        f"  MA150 : {currency}{cache.ma150:,.2f}  ({vs_ma150:+.1f}%)\n"
        f"  MA200 : {currency}{cache.ma200:,.2f}  ({vs_ma200:+.1f}%)\n\n"
        f"<b>ช่วง 52 สัปดาห์</b>\n"
        f"  สูงสุด: {currency}{cache.high52w:,.2f}  ({from52h:+.1f}%)\n"
        f"  ต่ำสุด: {currency}{cache.low52w:,.2f}  ({from52l:+.1f}%)\n"
        f"{'─' * 30}\n"
    )

    if cache.trend_score >= 7 and price > cache.pivot:
        msg += "⚡ <b>Breakout Zone — น่าจับตามอง</b>"
    elif cache.trend_score >= 7:
        msg += "👀 Trend ดี รอ Breakout"
    elif cache.trend_score <= 3:
        msg += "⚠️ Trend อ่อนแอ ยังไม่น่าสนใจ"
    else:
        msg += "😐 ยังไม่มีสัญญาณชัดเจน"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    if not _is_authorized(update):
        return

    msg = (
        "📖 <b>SEPA TradeBot — คำสั่งที่ใช้ได้</b>\n\n"
        "<b>/price SYMBOL EXCHANGE</b>\n"
        "  ดูราคาปัจจุบัน + แนวโน้ม\n"
        "  ตัวอย่าง: <code>/price GLD AMEX</code>\n\n"
        "<b>/buy SYMBOL EXCHANGE PRICE SHARES</b>\n"
        "  บันทึก position ใหม่\n"
        "  ตัวอย่าง: <code>/buy NVDA NASDAQ 210.50 678</code>\n\n"
        "<b>/positions</b>\n"
        "  แสดง open positions ทั้งหมด\n\n"
        "<b>/help</b>\n"
        "  แสดงคำสั่งนี้\n\n"
        "ระบบจะแจ้งเตือนอัตโนมัติเมื่อ:\n"
        "  • ราคาแตะ Stop Loss\n"
        "  • ราคาแตะ Target 1 (Sell Half)\n"
        "  • ราคาแตะ Target 2 (Sell All)\n"
        "  • ราคาหลุดต่ำกว่า MA50 (Trend Break)"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('price',     price_handler))
    app.add_handler(CommandHandler('buy',       buy_handler))
    app.add_handler(CommandHandler('positions', positions_handler))
    app.add_handler(CommandHandler('help',      help_handler))

    logger.info("SEPA TradeBot started — polling for commands")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
