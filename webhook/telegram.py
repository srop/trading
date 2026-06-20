"""Send formatted SEPA alert to Telegram."""
from __future__ import annotations
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
API_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def send_alert(message: str) -> bool:
    """Send message to Telegram. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    try:
        resp = httpx.post(API_URL, json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"Telegram error: {e}")
        return False


def format_alert(result, scored, ai_summary: str) -> str:
    """
    Format SEPA result into Telegram HTML message.

    result   = SEPAResult from src.analyzer
    scored   = FullScoreResult from webhook.analysis (wraps ScoreBreakdown +
               key_reasons, risk_factors, action_plan)
    ai_summary = short AI qualitative summary
    """
    currency = "฿" if result.exchange == "SET" else "$"
    rec_emoji = {
        "Strong Buy": "🟢",
        "Buy":        "🔵",
        "Watchlist":  "🟡",
        "Avoid":      "🟠",
        "Reject":     "🔴",
    }.get(scored.recommendation, "⚪")

    stop_pct = ((result.position.stop_loss - result.current_price) / result.current_price) * 100
    t1_pct   = ((result.position.target1   - result.current_price) / result.current_price) * 100
    t2_pct   = ((result.position.target2   - result.current_price) / result.current_price) * 100

    reasons_text = "\n".join(f"  • {r}" for r in scored.key_reasons[:3])
    risks_text   = "\n".join(f"  • {r}" for r in scored.risk_factors[:2])

    return (
        f"🚨 <b>SEPA BREAKOUT — {result.symbol} ({result.exchange})</b>\n"
        f"{'─'*35}\n"
        f"💰 ราคา: <b>{currency}{result.current_price:,.2f}</b>  |  "
        f"ปริมาณ: <b>{result.breakout.breakout_volume_ratio:.1f}x</b> เฉลี่ย\n"
        f"📊 Trend: <b>{result.trend.conditions_met}/9</b>  |  RS: <b>{result.rs.rating}</b>\n\n"
        f"{rec_emoji} <b>คะแนน: {scored.confidence_score:.0f}/100 → {scored.recommendation}</b>\n\n"
        f"<b>จุดเข้าและความเสี่ยง</b>\n"
        f"  เข้าซื้อ : {currency}{result.position.entry_low:,.2f} – {currency}{result.position.entry_high:,.2f}\n"
        f"  ตัดขาดทุน: {currency}{result.position.stop_loss:,.2f} ({stop_pct:+.1f}%)\n"
        f"  เป้าที่ 1 : {currency}{result.position.target1:,.2f} ({t1_pct:+.1f}%) → ขายครึ่ง\n"
        f"  เป้าที่ 2 : {currency}{result.position.target2:,.2f} ({t2_pct:+.1f}%) → ขายทั้งหมด\n"
        f"  R:R      : 1:{result.position.risk_reward:.1f}  |  จำนวน: {result.position.position_size:,} หุ้น\n\n"
        f"<b>วิเคราะห์โดย AI</b>\n"
        f"{ai_summary}\n\n"
        f"<b>เหตุผลหลัก</b>\n{reasons_text}\n\n"
        f"<b>ความเสี่ยง</b>\n{risks_text}\n"
        f"{'─'*35}\n"
        f"⚡ <b>แผนการ:</b> {scored.action_plan}"
    )
