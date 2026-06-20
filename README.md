# SEPA TradeBot

ระบบสแกนหุ้น Breakout อัตโนมัติตามแนวทาง Mark Minervini (SEPA Method) ส่งแจ้งเตือนผ่าน Telegram พร้อมวิเคราะห์ด้วย AI

---

## ระบบทำอะไรได้บ้าง

1. **สแกน Breakout อัตโนมัติ** — ตรวจสอบ SET100, NASDAQ100 และ Commodities ทุก 15 นาทีในช่วงเวลาตลาดเปิด แล้วส่งแจ้งเตือนมาที่ Telegram พร้อมคะแนน SEPA และ AI สรุปภาษาไทย
2. **ติดตาม Portfolio** — บันทึกการซื้อผ่าน Telegram Bot และเก็บข้อมูลใน Google Sheets
3. **แจ้งเตือนจุดขาย** — แจ้งอัตโนมัติเมื่อถึง Stop Loss, Target 1, Target 2 หรือ Trend Break (ต่ำกว่า MA50)

---

## ความต้องการของระบบ

- Python 3.11+
- Telegram Bot Token
- Google Cloud Service Account (สำหรับ Google Sheets)
- OpenRouter API Key

---

## การติดตั้ง

```bash
git clone <repo>
cd tradebot
pip install -r requirements.txt
```

---

## ตั้งค่า .env

สร้างไฟล์ `.env` ที่ root ของโปรเจกต์:

```env
# TradingView (ไม่จำเป็น — ใส่เพื่อเพิ่ม rate limit)
TV_USERNAME=
TV_PASSWORD=

# OpenRouter AI
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=deepseek/deepseek-r1

# Portfolio
PORTFOLIO_SIZE=1000000
RISK_PERCENT=0.01

# Telegram
TELEGRAM_BOT_TOKEN=1234567890:AAE...
TELEGRAM_CHAT_ID=1815111624

# Google Sheets
GOOGLE_SHEET_ID=1xQl3jxtfvGC6kCM59lAX...
CREDENTIALS_PATH=credentials.json

# เวลาเปิด-ปิดตลาด (HH:MM แบบ 24 ชั่วโมง)
SET_OPEN_AM_START=10:00
SET_OPEN_AM_END=12:30
SET_OPEN_PM_START=14:30
SET_OPEN_PM_END=16:30

NASDAQ_OPEN_START=09:30
NASDAQ_OPEN_END=16:00

GOLD_OPEN_START=08:00
GOLD_OPEN_END=21:00
GOLD_OPEN_WEEKENDS=true
```

---

## ตั้งค่า Google Sheets

1. ไปที่ [Google Cloud Console](https://console.cloud.google.com) → สร้าง Service Account
2. ดาวน์โหลด credentials JSON และบันทึกเป็น `credentials.json` ที่ root ของโปรเจกต์
3. สร้าง Google Sheet ใหม่ และ Share ให้ email ของ Service Account (Editor)
4. คัดลอก Sheet ID จาก URL แล้วใส่ใน `GOOGLE_SHEET_ID`

Sheet ต้องมี tab ชื่อ **Positions** พร้อม header แถวแรก:

```
Symbol | Exchange | Entry Price | Entry Date | Shares | Stop Loss | Target 1 | Target 2 | Status | Exit Price | Exit Date | PnL%
```

---

## วิธีรันระบบ

### รันระบบหลัก (แนะนำ)

```bash
python start.py
```

รันคำสั่งเดียว เปิดทั้ง Scanner + Telegram Bot พร้อมกัน

### รันแยก (ถ้าต้องการ debug)

```bash
python runner.py   # สแกน Breakout + ตรวจจุดขาย
python bot.py      # Telegram Bot รับคำสั่ง /buy /positions
```

### Screen — สแกนด้วยตนเอง (CLI)

```bash
python screen.py SET
python screen.py NASDAQ
python screen.py COMMODITIES
python screen.py all
```

---

## คำสั่ง Telegram Bot

| คำสั่ง | รูปแบบ | ตัวอย่าง |
|--------|--------|---------|
| `/buy` | `/buy SYMBOL EXCHANGE PRICE SHARES` | `/buy NVDA NASDAQ 210.50 678` |
| `/positions` | `/positions` | แสดง open positions ทั้งหมด |
| `/help` | `/help` | แสดงคำสั่งทั้งหมด |

**EXCHANGE ที่รองรับ:** `SET` `NASDAQ` `NYSE` `AMEX` `COMEX`

---

## เงื่อนไข Breakout (SEPA)

ระบบจะส่งแจ้งเตือนเมื่อหุ้นผ่านเงื่อนไขครบ:

- ราคาปิดเหนือ 50-day High
- Volume ≥ 1.5 เท่าของค่าเฉลี่ย
- Trend Template ≥ 7/9 ตามเงื่อนไข Minervini
- ราคาไม่ห่างจาก Pivot เกิน 10% (ยังไม่ extended)
- คัดเฉพาะ 10 อันดับแรกที่มี Volume สูงที่สุดต่อตลาด

---

## แจ้งเตือนจุดขาย

| เงื่อนไข | การดำเนินการ |
|---------|------------|
| ราคา ≤ Stop Loss | ขายทันที |
| ราคา ≥ Target 1 (+20%) | ขายครึ่ง |
| ราคา ≥ Target 2 (+40%) | ขายทั้งหมด |
| ราคา < MA50 รายวัน | ขายทันที (Trend Break) |

---

## โครงสร้างโปรเจกต์

```
tradebot/
├── runner.py          # Main loop — สแกน Breakout + ตรวจจุดขาย
├── bot.py             # Telegram Bot — รับคำสั่ง /buy /positions
├── screen.py          # CLI scan แบบ manual
├── src/
│   ├── analyzer.py    # SEPA 12-phase analysis
│   ├── breakout.py    # ตรวจ Breakout จาก 15min bars
│   ├── exit_monitor.py # ตรวจเงื่อนไขจุดขาย
│   ├── scoring.py     # คะแนน SEPA 0-100
│   ├── sheets.py      # Google Sheets CRUD
│   └── config.py      # ค่า config จาก .env
├── webhook/
│   ├── analysis.py    # รัน SEPA + AI summary
│   └── telegram.py    # ส่งข้อความ Telegram
└── data/
    ├── set100_stocks.csv
    ├── nasdaq100_stocks.csv
    └── commodities.csv
```
