# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

```bash
# Setup
python -m pip install -r requirements.txt

# Run the trading bot (requires .env with API credentials)
python main.py

# Run tests
pytest tests/
pytest tests/test_strategy.py::test_name  # Run specific test

# Code quality
pylint *.py tests/

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

## Development Setup

- **Python version:** 3.10 or higher required
- **Virtual environment:** Recommended (e.g., `python -m venv venv`)
- **Dependencies:** Install with `pip install -r requirements.txt`
- **Environment variables:** Create `.env` file with `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`
- **Key imports pattern:** Modules use type hints throughout; check function signatures for parameter types

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
- **Router-based command handling:** Uses aiogram 3.x Router pattern with decorators (`@router.message(Command(...))`)
- **Commands:** `/start`, `/help`, `/check_rebalance`, `/info`, `/portfolio`, `/stats`, `/settings`
- **Admin notifications:** Sent to IDs in `config.ADMIN_IDS` (startup notification on launch, countdown 1 hour before rebalance)
- **Error handling:** `@telegram_handler` decorator wraps async command handlers with try-catch and user-friendly error messages
- **Async pattern:** All handlers are async functions; bot dispatcher runs concurrently with APScheduler

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

1. **Retry Mechanism** - `@retry_on_exception` decorator in utils.py handles API failures (3 attempts with 1-second delays by default)
   - Used on `get_signals()` (strategy) and `get_positions()` (utils)
   - Raises exception after final attempt; calling code handles gracefully

2. **Timezone Handling** - `NY_TIMEZONE = pytz.timezone('America/New_York')` constant used throughout
   - Market schedule uses NY time, rebalance scheduled at 10:00 AM NY
   - Prevents timezone-related bugs in scheduling

3. **Market Validation** - `MarketSchedule` class validates market hours before trading
   - Uses Alpaca clock API (`trading_client.get_clock()`)
   - Prevents accidental trades outside market hours

4. **State Persistence** - File-based flag system prevents duplicate rebalances
   - Path: `data/last_rebalance.txt`
   - Checked before each rebalance to ensure >22 trading days have elapsed
   - Survives bot restart (critical for long-running services)

5. **Paper Trading** - Default safe mode for development/testing
   - Configured via Alpaca API client initialization
   - Change `paper=True` to `paper=False` for live trading (high risk)

6. **strategy.py is immutable** - Do not modify this file
   - Core trading logic must remain stable and unchanged
   - Add new functionality in `main.py` (TradingBot methods) or `handlers.py` (Telegram commands)
   - If new strategy features are needed, discuss scope first

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

## Data Directory Structure

- `last_rebalance.txt` - Tracks date of last rebalance (single line, updated on each rebalance)
- `trading_bot.log` - Rotating log file with console + file output (initialized in main.py)
- `trades_history.csv` - Historical trade records for analysis
- `portfolio_performance.png` - Backtest results visualization
- `all_orders.xlsx` - Exported trading orders spreadsheet
- `scripts/export_orders.py` - Utility to export Alpaca orders to Excel
- `notebooks/` - Jupyter notebooks for analysis and experimentation

## Notable Implementation Details

- **Paper Trading Default** - Safe for testing; change in TradingClient initialization (currently `paper=True`)
- **Concurrent Tasks** - Telegram bot dispatcher (`aiogram`) runs async alongside APScheduler's background scheduler
- **Logging** - Dual output to console and `data/trading_bot.log` via `logging.basicConfig(handlers=[...])`
- **Position Tracking** - Uses Alpaca position API (`trading_client.get_all_positions()`), no local database required
- **Backtesting** - Separate simulation module with `FakeAccount` and `FakePosition` classes for testing strategy logic

## Common Debugging Approaches

1. **Check API credentials:** Ensure `.env` has valid `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`
2. **Review logs:** Check `data/trading_bot.log` for detailed error messages with timestamps
3. **Test strategy in isolation:** Run `python backtest.py` to validate momentum calculations without trading
4. **Test with specific test file:** `pytest tests/test_strategy.py -v` to debug strategy issues
5. **Check market hours:** Verify trading time is within NYSE hours using `MarketSchedule.is_open_now()`
6. **Review rebalance flag:** Check `data/last_rebalance.txt` to see if rebalance was already executed
7. **Monitor Telegram:** Check admin chat for bot notifications to verify Telegram integration works
