# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

```bash
# Run the trading bot
python main.py

# Run tests
pytest tests/

# Run backtesting with charts and CSV export
python backtest.py

# Export all orders to Excel
python data/scripts/export_orders.py
```

## Project Overview

**alpaca_bot** is an automated momentum-based trading bot that:
- Trades the top 10 S&P 500 stocks by momentum (1-year returns)
- Rebalances every 22 trading days at 10:00 AM NY time
- Provides Telegram interface for monitoring and admin notifications
- Uses Alpaca Markets API (paper trading by default)
- Implements persistent state management and comprehensive error handling

**Language:** Python 3.10+ | **Main Dependencies:** alpaca-py, yfinance, APScheduler, aiogram

## Architecture & Core Components

The bot has three main layers:

### 1. Trading Core (main.py)
- **TradingBot** - Main orchestrator, manages Alpaca API connection and rebalancing scheduler
- **PortfolioManager** - Manages current positions and interacts with MomentumStrategy
- **RebalanceFlag** - Persistent state manager using `data/last_rebalance.txt` to track date of last rebalance and prevent duplicate runs
- **MarketSchedule** - NYSE market hours validator and trading day counter (handles weekends/holidays)

**Key insight:** RebalanceFlag uses file-based persistence to survive bot restarts. The flag is checked daily but rebalancing only executes if the last rebalance date was >22 trading days ago. This prevents accidental duplicate rebalances within the same day.

### 2. Strategy (strategy.py)
- **MomentumStrategy** - Downloads 1-year price history for all S&P 500 stocks, calculates momentum (total return %), ranks them, and selects top 10
- Uses yfinance for data retrieval
- Equal-weight allocation for selected stocks
- Automatically closes positions not in top 10 and opens new top 10 positions

### 3. Telegram Interface (handlers.py + main.py)
- Commands: `/start`, `/help`, `/check_rebalance`, `/info`, `/portfolio`, `/stats`, `/settings`
- Admin notifications sent to IDs in `config.ADMIN_IDS`
- Startup notification on bot launch
- Countdown notification 1 hour before each rebalance (sent once per day)

## Configuration

**Environment Variables** (.env required):
```
ALPACA_API_KEY=<key>
ALPACA_SECRET_KEY=<secret>
TELEGRAM_BOT_TOKEN=<token>
```

**Constants** (config.py):
- `ADMIN_IDS` - List of Telegram chat IDs for admin notifications
- `REBALANCE_INTERVAL_DAYS` - Set to 22 trading days
- `snp500_tickers` - Complete S&P 500 ticker list (~500 stocks)

## Testing

All tests use pytest fixtures (conftest.py) with mocks for:
- Alpaca trading client
- yfinance price data
- Telegram messages
- File I/O

Run tests: `pytest tests/` or `pytest tests/test_strategy.py::test_name` for specific tests.

## Design Patterns & Key Details

1. **Retry Mechanism** - `@retry_on_exception` decorator in utils.py handles API failures (3 attempts)
2. **Timezone Handling** - All times use America/New_York timezone
3. **Market Validation** - Bot only acts during NYSE market hours
4. **State Persistence** - Rebalance date stored in data/last_rebalance.txt (file checked before each run)
5. **Paper Trading** - Default safe mode for development (configurable via Alpaca API parameter)

## Data Flow

1. Bot starts → Validates market schedule → Schedules 10:00 AM rebalancing
2. At rebalancing time:
   - Check if already rebalanced today (via RebalanceFlag)
   - Download 1-year data for S&P 500
   - Calculate momentum scores and identify top 10
   - Close non-top-10 positions
   - Open top-10 positions with equal weight
   - Write new rebalance date to file
3. Telegram commands query bot state and return formatted responses

## Notable Implementation Details

- **Paper Trading Default** - Safe for testing, change in Alpaca client initialization
- **Concurrent Tasks** - Telegram bot runs async alongside market scheduler
- **Logging** - Dual output to console and `data/trading_bot.log`
- **Position Tracking** - Uses Alpaca position API, no local database required
