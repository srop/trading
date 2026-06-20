import os
from dotenv import load_dotenv

load_dotenv()

EXCHANGES: dict[str, dict] = {
    'NASDAQ': {
        'screener': 'america',
        'yf_suffix': '',
        'index': 'SPY',
        'index_exchange': 'AMEX',
    },
    'NYSE': {
        'screener': 'america',
        'yf_suffix': '',
        'index': 'SPY',
        'index_exchange': 'AMEX',
    },
    'AMEX': {
        'screener': 'america',
        'yf_suffix': '',
        'index': 'SPY',
        'index_exchange': 'AMEX',
    },
    'COMEX': {
        'screener': 'america',
        'yf_suffix': '',
        'index': 'GLD',
        'index_exchange': 'AMEX',
    },
    'SET': {
        'screener': 'thailand',
        'yf_suffix': '.BK',
        'index': 'SET50',
        'index_exchange': 'SET',
    },
}

PORTFOLIO_SIZE: float = float(os.getenv('PORTFOLIO_SIZE', '1000000'))
RISK_PERCENT: float = float(os.getenv('RISK_PERCENT', '0.01'))

# TradingView credentials (optional — increases data access)
TV_USERNAME: str = os.getenv('TV_USERNAME', '')
TV_PASSWORD: str = os.getenv('TV_PASSWORD', '')

# OpenRouter AI
OPENROUTER_API_KEY: str = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL: str = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')

# Google Sheets portfolio tracker
GOOGLE_SHEET_ID: str  = os.getenv('GOOGLE_SHEET_ID', '')
CREDENTIALS_PATH: str = os.getenv('CREDENTIALS_PATH', 'credentials.json')

# Market hours
SET_OPEN_AM_START:  str  = os.getenv('SET_OPEN_AM_START',  '10:00')
SET_OPEN_AM_END:    str  = os.getenv('SET_OPEN_AM_END',    '12:30')
SET_OPEN_PM_START:  str  = os.getenv('SET_OPEN_PM_START',  '14:30')
SET_OPEN_PM_END:    str  = os.getenv('SET_OPEN_PM_END',    '16:30')

NASDAQ_OPEN_START:  str  = os.getenv('NASDAQ_OPEN_START',  '09:30')
NASDAQ_OPEN_END:    str  = os.getenv('NASDAQ_OPEN_END',    '16:00')

GOLD_OPEN_START:    str  = os.getenv('GOLD_OPEN_START',    '08:00')
GOLD_OPEN_END:      str  = os.getenv('GOLD_OPEN_END',      '21:00')
GOLD_OPEN_WEEKENDS: bool = os.getenv('GOLD_OPEN_WEEKENDS', 'true').lower() == 'true'
