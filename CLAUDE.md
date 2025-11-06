# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

```bash
# Setup
python -m pip install -r requirements.txt

# Run the trading bot (requires .env with API credentials)
python bot.py

# Run tests
pytest tests/
pytest tests/test_strategy.py::test_name  # Run specific test

# Code quality
pylint *.py tests/

# Run backtesting with charts and CSV export
python backtest.py
```

## Project Overview

**alpaca_bot** is an automated momentum-based trading bot that:
- Trades the top 10 S&P 500 stocks by momentum (1-year returns)
- Rebalances every 22 trading days at 10:00 AM NY time
- Provides Telegram interface for monitoring and admin notifications
- Uses Alpaca Markets API (paper trading by default)
- Implements persistent state management and comprehensive error handling

**Language:** Python 3.10+ | **Main Dependencies:** alpaca-py, yfinance, APScheduler, aiogram

## Development Setup

- **Python version:** 3.10 or higher required
- **Virtual environment:** Recommended (e.g., `python -m venv venv`)
- **Dependencies:** Install with `pip install -r requirements.txt`
- **Environment variables:** Create `.env` file with `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `ENVIRONMENT`
- **Key imports pattern:** Modules use type hints throughout; check function signatures for parameter types

## Architecture & Core Components

The bot has three main layers:

### 1. Trading Core (bot.py)
- **TradingBot** - Main orchestrator, manages Alpaca API connection, scheduling, and portfolio state
  - Key methods: `start()`, `run_rebalance()`, `calculate_days_until_rebalance()`, `get_rebalance_preview()`, `get_next_rebalance_date()`
  - Handles admin notifications: startup message and 1-hour countdown before rebalance
- **RebalanceFlag** - Persistent state manager using `data/last_rebalance.txt` to track date of last rebalance
  - Prevents duplicate rebalancing within the same day by checking if >22 trading days have elapsed
  - File-based persistence survives bot restarts
  - Methods: `should_rebalance()`, `set_rebalanced()`, `get_countdown_message()`
- **MarketSchedule** - NYSE market hours validator
  - Uses Alpaca clock API to validate trading hours
  - Counts trading days (handles weekends/holidays)
  - Methods: `is_open_now()`, `get_next_open_time()`
- **TelegramLoggingHandler** - Custom logging handler that sends ERROR logs to Telegram admins

**Key insight:** The rebalancing logic is split: `bot.py` manages scheduling and state, while `strategy.py` handles position management. RebalanceFlag file-based persistence ensures atomicity and prevents accidental duplicate rebalances.

### 2. Strategy (strategy.py - IMMUTABLE)
- **MomentumStrategy** - Core trading logic (DO NOT MODIFY THIS FILE)
  - `get_signals()` - Downloads 1-year price history for all S&P 500 stocks, calculates momentum (total return %), ranks, selects top 10
  - `close_positions()` - Close positions not in top 10
  - `open_positions()` - Open new top 10 positions with equal-weight allocation
  - `rebalance()` - Orchestrates close/open operations
  - Uses yfinance for data, equal-weight allocation for new positions
  - Includes error recovery: failed position closures/opens are logged but don't block rebalancing
  - **Note:** This file is immutable. Add new functionality in `bot.py` (TradingBot methods) or `handlers.py` (Telegram commands)

### 3. Telegram Interface (handlers.py + bot.py)
- **Router-based command handling:** Uses aiogram 3.x Router pattern with decorators (`@router.message(Command(...))`)
- **Commands:** `/start`, `/help`, `/check_rebalance`, `/test_rebalance`, `/info`, `/portfolio`, `/stats`, `/settings`, `/clear`
- **Admin notifications:** Sent to IDs in `config.ADMIN_IDS` (startup + 1-hour countdown)
- **Error handling:** `@telegram_handler` decorator wraps async handlers with try-catch and user-friendly error messages
- **Async pattern:** All handlers are async; bot dispatcher runs concurrently with APScheduler

### 4. Data Management (data_loader.py)
- **DataLoader** - Centralized market data loading with caching
  - `load_market_data()` - Fetches from cache (24h validity) or yfinance
  - `get_snp500_tickers()` - Fetches from Wikipedia with fallback to `config.snp500_tickers`
  - Cache stored in `data/cache.pkl` (pickle format)
  - Includes custom tickers via `config.CUSTOM_TICKERS`

## Configuration

**Environment Variables** (.env required):
```
ALPACA_API_KEY=<key>
ALPACA_SECRET_KEY=<secret>
TELEGRAM_BOT_TOKEN=<token>
ENVIRONMENT=local|prod  # local shows progress bars, prod hides them
```

**Constants** (config.py):
- `ADMIN_IDS` - List of Telegram chat IDs for admin notifications
- `REBALANCE_INTERVAL_DAYS` - Set to 22 trading days
- `CUSTOM_TICKERS` - Additional tickers beyond S&P 500 (e.g., RGTI, QBTS, QUBT)
- `snp500_tickers` - Fallback S&P 500 list (~500 stocks) if Wikipedia fetch fails

## Testing

All tests use pytest fixtures (conftest.py) with mocks for:
- Alpaca trading client
- yfinance price data
- Telegram messages
- File I/O

Run tests: `pytest tests/` or `pytest tests/test_strategy.py::test_name` for specific tests.

## Design Patterns & Key Details

1. **Retry Mechanism** - `@retry_on_exception` decorator in utils.py handles API failures
   - Default: 3 attempts with 1-second delays
   - Used on `get_signals()` (strategy) and `get_positions()` (utils)
   - Raises exception after final attempt; calling code handles gracefully

2. **Timezone Handling** - `NY_TIMEZONE = pytz.timezone('America/New_York')` constant
   - Market schedule uses NY time, rebalance scheduled at 10:00 AM NY
   - Prevents timezone-related bugs in scheduling

3. **Market Validation** - `MarketSchedule` class validates market hours before trading
   - Uses Alpaca clock API (`trading_client.get_clock()`)
   - Prevents accidental trades outside market hours

4. **State Persistence** - File-based flag system prevents duplicate rebalances
   - Path: `data/last_rebalance.txt`
   - Checked before each rebalance to ensure >22 trading days have elapsed
   - Single-line format: ISO date string (survives bot restarts)

5. **Paper Trading** - Default safe mode for development/testing
   - Configured via Alpaca API client initialization (currently `paper=True`)
   - Change to `paper=False` for live trading (use extreme caution)

6. **Caching Strategy** - 24-hour cache for market data
   - Reduces API calls to yfinance
   - Cache file path: `data/cache.pkl`
   - Cache validity checked before each `load_market_data()` call

7. **Error Resilience** - Position close/open operations don't block rebalancing
   - Failed positions logged as warnings
   - Rebalancing completes even if some positions fail
   - Telegram admins notified of errors via logging handler

## Data Flow

1. Bot starts → Validates market schedule → Schedules 10:00 AM rebalancing
2. At rebalancing time:
   - Check if already rebalanced today (via RebalanceFlag)
   - If not, calculate days since last rebalance
   - If >22 trading days, trigger full rebalance:
     - Download 1-year data for S&P 500 (from cache or yfinance)
     - Calculate momentum scores and identify top 10
     - Close non-top-10 positions
     - Open top-10 positions with equal weight
     - Write new rebalance date to file
3. Telegram commands query bot state and return formatted responses
4. ERROR logs automatically sent to Telegram admins

## Data Directory Structure

- `last_rebalance.txt` - Tracks date of last rebalance (single line, ISO format)
- `cache.pkl` - 24-hour cache of market data (pickle format)
- `trading_bot.log` - Rotating log file with console + file output
- `trades_history.csv` - Historical trade records for analysis
- `portfolio_performance.png` - Backtest results visualization
- `all_orders.xlsx` - Exported trading orders spreadsheet

## Notable Implementation Details

- **Paper Trading Default** - Safe for testing; change `paper=True` to `paper=False` in `TradingBot.__init__` (high risk)
- **Concurrent Tasks** - Telegram bot dispatcher (aiogram) runs async alongside APScheduler's background scheduler
- **Logging** - Dual output to console and `data/trading_bot.log` via `logging.basicConfig(handlers=[...])`
- **Position Tracking** - Uses Alpaca position API (`trading_client.get_all_positions()`), no local database
- **Backtesting** - Separate simulation module with `FakeAccount` and `FakePosition` classes

## Common Debugging Approaches

1. **Check API credentials:** Ensure `.env` has valid `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`
2. **Review logs:** Check `data/trading_bot.log` for detailed error messages with timestamps
3. **Test strategy in isolation:** Run `python backtest.py` to validate momentum calculations without trading
4. **Test with specific test file:** `pytest tests/test_strategy.py -v` to debug strategy issues
5. **Check market hours:** Verify trading time is within NYSE hours using `MarketSchedule.is_open_now()`
6. **Review rebalance flag:** Check `data/last_rebalance.txt` to see if rebalance was already executed
7. **Monitor Telegram:** Check admin chat for bot notifications to verify Telegram integration works
8. **Clear cache if stale:** Delete `data/cache.pkl` to force fresh data download from yfinance
