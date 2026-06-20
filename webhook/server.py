"""
FastAPI webhook server — receives TradingView SEPA breakout alerts.

Run:
    uvicorn webhook.server:app --host 0.0.0.0 --port 8080 --reload

With ngrok:
    ngrok http 8080
    → copy HTTPS URL → paste into TradingView alert webhook URL
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

from .analysis import run_breakout_analysis
from .telegram import send_alert, format_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SEPA Webhook", version="1.0.0")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def _verify_secret(payload: bytes, signature: str) -> bool:
    """Optional HMAC verification if WEBHOOK_SECRET is set."""
    if not WEBHOOK_SECRET:
        return True
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def receive_alert(request: Request):
    body = await request.body()
    sig  = request.headers.get("X-Signature", "")

    if not _verify_secret(body, sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    ticker   = data.get("ticker", "").upper().strip()
    exchange = data.get("exchange", "").upper().strip()

    if not ticker or not exchange:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing ticker or exchange",
        )

    logger.info(f"Breakout alert received: {ticker} ({exchange})")

    try:
        result, scored, ai_summary = run_breakout_analysis(ticker, exchange, data)
        message = format_alert(result, scored, ai_summary)
        sent    = send_alert(message)

        logger.info(
            f"Analysis done: {ticker} score={scored.confidence_score:.0f} "
            f"rec={scored.recommendation} telegram={'sent' if sent else 'failed'}"
        )

        return JSONResponse({
            "status": "ok",
            "ticker": ticker,
            "score": scored.confidence_score,
            "recommendation": scored.recommendation,
        })

    except Exception as e:
        logger.exception(f"Analysis failed for {ticker}: {e}")
        # Still try to send error alert to Telegram
        send_alert(
            f"⚠️ <b>SEPA Alert Error</b>\n{ticker} ({exchange})\n"
            f"<code>{str(e)[:200]}</code>"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
