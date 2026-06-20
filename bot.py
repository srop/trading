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

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    if not _is_authorized(update):
        return

    msg = (
        "📖 <b>SEPA TradeBot — คำสั่งที่ใช้ได้</b>\n\n"
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
    app.add_handler(CommandHandler('buy',       buy_handler))
    app.add_handler(CommandHandler('positions', positions_handler))
    app.add_handler(CommandHandler('help',      help_handler))

    logger.info("SEPA TradeBot started — polling for commands")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
