"""Google Sheets portfolio tracker."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

logger = logging.getLogger(__name__)

SHEET_ID         = os.getenv('GOOGLE_SHEET_ID', '')
CREDENTIALS_PATH = os.getenv('CREDENTIALS_PATH', 'credentials.json')
SHEET_NAME       = 'Positions'
SCOPES           = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]

HEADERS = [
    'Symbol', 'Exchange', 'Entry Price', 'Entry Date', 'Shares',
    'Stop Loss', 'Target 1', 'Target 2', 'Status', 'Exit Price', 'Exit Date', 'PnL%',
]


@dataclass
class Position:
    row: int               # sheet row number (for update)
    symbol: str
    exchange: str
    entry_price: float
    entry_date: str        # YYYY-MM-DD
    shares: int
    stop_loss: float
    target1: float
    target2: float
    status: str            # "Open" | "Closed"
    exit_price: Optional[float] = None
    exit_date: Optional[str] = None
    pnl_pct: Optional[float] = None


def _get_sheet() -> gspread.Worksheet:
    """Authorize and return the Positions worksheet, creating it if absent."""
    import json, base64
    raw = os.getenv('GOOGLE_CREDENTIALS_JSON', '')
    if raw:
        info = json.loads(base64.b64decode(raw).decode() if '\\n' not in raw and '{' not in raw else raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    # Find or create the worksheet
    worksheet_titles = [ws.title for ws in spreadsheet.worksheets()]
    if SHEET_NAME not in worksheet_titles:
        ws = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS)
        logger.info(f"Created worksheet '{SHEET_NAME}' with headers")
    else:
        ws = spreadsheet.worksheet(SHEET_NAME)

    return ws


def add_position(
    symbol: str,
    exchange: str,
    entry_price: float,
    shares: int,
    stop_loss: float,
    target1: float,
    target2: float,
) -> Position:
    """Append a new open position to the sheet and return the Position object."""
    ws = _get_sheet()
    entry_date = datetime.now().strftime('%Y-%m-%d')

    row_data = [
        symbol.upper(),
        exchange.upper(),
        entry_price,
        entry_date,
        shares,
        stop_loss,
        target1,
        target2,
        'Open',
        '',   # Exit Price
        '',   # Exit Date
        '',   # PnL%
    ]
    ws.append_row(row_data)

    # Row number: count existing rows after append
    all_rows = ws.get_all_values()
    row_num = len(all_rows)  # last row

    logger.info(f"Added position: {symbol} @ {entry_price} row={row_num}")

    return Position(
        row=row_num,
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        entry_price=entry_price,
        entry_date=entry_date,
        shares=shares,
        stop_loss=stop_loss,
        target1=target1,
        target2=target2,
        status='Open',
    )


def get_open_positions() -> list[Position]:
    """Return all rows where Status == 'Open'."""
    ws = _get_sheet()
    records = ws.get_all_records()  # list of dicts using row 1 as header

    positions: list[Position] = []
    for i, rec in enumerate(records):
        if str(rec.get('Status', '')).strip() != 'Open':
            continue

        def _f(key: str) -> Optional[float]:
            v = rec.get(key, '')
            try:
                return float(v) if v not in ('', None) else None
            except (ValueError, TypeError):
                return None

        pos = Position(
            row=i + 2,  # row 1 is header, data starts at row 2
            symbol=str(rec.get('Symbol', '')).strip(),
            exchange=str(rec.get('Exchange', '')).strip(),
            entry_price=_f('Entry Price') or 0.0,
            entry_date=str(rec.get('Entry Date', '')).strip(),
            shares=int(rec.get('Shares', 0) or 0),
            stop_loss=_f('Stop Loss') or 0.0,
            target1=_f('Target 1') or 0.0,
            target2=_f('Target 2') or 0.0,
            status='Open',
            exit_price=_f('Exit Price'),
            exit_date=str(rec.get('Exit Date', '')).strip() or None,
            pnl_pct=_f('PnL%'),
        )
        positions.append(pos)

    return positions


def close_position(position: Position, exit_price: float, reason: str) -> None:
    """
    Mark a position as Closed in the sheet.
    reason is used only for logging — not stored in the sheet.
    """
    ws = _get_sheet()
    exit_date = datetime.now().strftime('%Y-%m-%d')

    pnl_pct = (
        (exit_price - position.entry_price) / position.entry_price * 100
        if position.entry_price
        else 0.0
    )

    # Columns: I=Status(9), J=Exit Price(10), K=Exit Date(11), L=PnL%(12)
    ws.update_cell(position.row, 9,  'Closed')
    ws.update_cell(position.row, 10, exit_price)
    ws.update_cell(position.row, 11, exit_date)
    ws.update_cell(position.row, 12, round(pnl_pct, 2))

    logger.info(
        f"Closed position: {position.symbol} row={position.row} "
        f"exit={exit_price} pnl={pnl_pct:+.1f}% reason={reason}"
    )
