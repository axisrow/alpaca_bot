# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start Commands

```bash
# Setup
python -m pip install -r requirements.txt

# Run the paper trading bot (requires .env with API credentials)
python bot.py

# Run tests
pytest tests/
pytest tests/test_strategy.py::test_name  # Run specific test

# Code quality
pylint *.py handlers.py strategies/

# Run backtesting with charts and CSV export
python backtest.py
```

## Project Overview

**alpaca_bot** is a multi-strategy momentum-based trading bot that:
- Supports multiple independent trading strategies (paper_low, paper_medium, live) with separate accounts
- Trades by momentum (1-year returns) with strategy-specific stock universes
- Paper strategies rebalance every 22 trading days at 10:00 AM NY time
- Live strategy includes investor account management and multi-tier allocation (low/medium/high)
- Provides Telegram interface for monitoring and admin notifications
- Uses Alpaca Markets API with paper trading defaults
- Implements persistent state management and comprehensive error handling

**Language:** Python 3.12+ | **Main Dependencies:** alpaca-py, yfinance, APScheduler, aiogram

## Development Setup

- **Python version:** 3.12 or higher required (uses Python 3.12 features)
- **Virtual environment:** Recommended (e.g., `python -m venv venv`)
- **Dependencies:** Install with `pip install -r requirements.txt`
- **Environment variables:** Create `.env` file with:
  - Paper trading: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `ENVIRONMENT`
  - Live trading (optional): `ALPACA_API_KEY_LIVE`, `ALPACA_SECRET_KEY_LIVE`, `INVESTORS_REGISTRY_PATH`
- **Key imports pattern:** Modules use type hints throughout; check function signatures for parameter types

## Architecture & Core Components

### 1. Multi-Strategy System (strategies/ directory)
- **Strategy Pattern:** Each strategy is a standalone class with identical interface
  - Classes: `PaperLowStrategy`, `PaperMediumStrategy`, `PaperHighStrategy`, `LiveStrategy`
  - Each has own API credentials, ticker universe, TOP_COUNT, and ENABLED flag
  - All inherit same `get_signals()`, `close_positions()`, `open_positions()`, `rebalance()` interface

- **Strategy-Specific Configurations (config.py)**
  - `PaperLowStrategy`: 50 top stocks from S&P 500 only (SNP500_TICKERS)
  - `PaperMediumStrategy`: 50 top stocks from S&P 500 + MEDIUM_TICKERS (RGTI, QBTS, QUBT)
  - `PaperHighStrategy`: 50 top stocks from extended high-volatility list (HIGH_TICKERS)
  - `LiveStrategy`: Top 50 from all combined tickers + investor account management

- **Separate Alpaca Accounts**
  - Paper accounts use `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`
  - Live account uses `ALPACA_API_KEY_LIVE`, `ALPACA_SECRET_KEY_LIVE`
  - Each strategy maintains independent positions and state

### 2. Trading Core (bot.py)
- **TradingBot** - Main orchestrator, manages scheduling and portfolio state
  - Handles paper trading strategies only (paper_low, paper_medium, paper_high)
  - Key methods: `start()`, `run_rebalance()`, `calculate_days_until_rebalance()`, `get_rebalance_preview()`, `get_next_rebalance_date()`
  - Handles admin notifications: startup message and 1-hour countdown before rebalance
- **RebalanceFlag** - Persistent state manager using `data/last_rebalance.txt`
  - Tracks date of last rebalance
  - Prevents duplicate rebalancing within same day by checking if >22 trading days have elapsed
  - File-based persistence survives bot restarts
  - Methods: `should_rebalance()`, `set_rebalanced()`, `get_countdown_message()`
- **MarketSchedule** - NYSE market hours validator
  - Uses Alpaca clock API to validate trading hours
  - Counts trading days (handles weekends/holidays)
  - Methods: `is_open_now()`, `get_next_open_time()`
- **TelegramLoggingHandler** - Custom logging handler that sends ERROR logs to Telegram admins

### 3. Investor Management (investor_manager.py - Live Account Only)
- **InvestorManager** - Manages multiple investor accounts within live strategy
  - Loads investor registry from CSV (`investors_registry.csv`)
  - Per-investor tracking: name, creation date, fee %, high watermark, last fee date, status
  - Pending operations system: deposits, withdrawals, fee distributions
  - Account allocation: Default split {low: 45%, medium: 35%, high: 20%}
  - Methods: `deposit()`, `withdraw()`, `process_pending_operations()`, `calculate_fees()`, `get_investor_path()`
- **CSV Format** (`investors_registry.csv`):
  - Columns: name, creation_date, fee_percent, is_fee_receiver, high_watermark, last_fee_date, status
  - Investor-specific files stored in `data/investors/{investor_name}/`

### 4. Telegram Interface (handlers.py + bot.py)
- **Router-based command handling:** Uses aiogram 3.x Router pattern with decorators
- **Commands:** `/start`, `/help`, `/check_rebalance`, `/test_rebalance`, `/info`, `/portfolio`, `/stats`, `/settings`, `/clear`
- **Admin notifications:** Sent to IDs in `config.ADMIN_IDS` (startup + 1-hour countdown)
- **Error handling:** `@telegram_handler` decorator wraps async handlers with try-catch and user-friendly error messages
- **Async pattern:** All handlers are async; bot dispatcher runs concurrently with APScheduler

### 5. Data Management (data_loader.py)
- **DataLoader** - Centralized market data loading with caching
  - `load_market_data()` - Fetches from cache (24h validity) or yfinance
  - `get_snp500_tickers()` - Fetches from Wikipedia with fallback to `config.SNP500_TICKERS`
  - Cache stored in `data/cache.pkl` (pickle format)
  - Supports combined ticker lists: S&P 500 + MEDIUM_TICKERS + CUSTOM_TICKERS + HIGH_TICKERS

## Configuration

**Environment Variables** (.env required):
```
# Paper trading (required for bot.py)
ALPACA_API_KEY=<paper-key>
ALPACA_SECRET_KEY=<paper-secret>
TELEGRAM_BOT_TOKEN=<token>
ENVIRONMENT=local|prod  # local shows progress bars, prod hides them

# Live trading (optional, for live strategy)
ALPACA_API_KEY_LIVE=<live-key>
ALPACA_SECRET_KEY_LIVE=<live-secret>
INVESTORS_REGISTRY_PATH=investors_registry.csv
```

**Constants** (config.py):
- `ADMIN_IDS` - List of Telegram chat IDs for admin notifications
- `REBALANCE_INTERVAL_DAYS` - Set to 22 trading days
- `CUSTOM_TICKERS` - Tickers added to all strategies (RGTI, QBTS, QUBT)
- `SNP500_TICKERS` - S&P 500 reference list (~500 stocks), used by PaperLowStrategy
- `MEDIUM_TICKERS` - Mid-cap/growth tickers for PaperMediumStrategy
- `HIGH_TICKERS` - Extended list of high-volatility tickers for PaperHighStrategy

## Testing

All tests use pytest fixtures (conftest.py) with mocks for:
- Alpaca trading client
- yfinance price data
- Telegram messages
- File I/O

Run tests: `pytest tests/` or `pytest tests/test_strategy.py::test_name` for specific tests.

## Design Patterns & Key Details

1. **Strategy Selector Pattern** - Each strategy is independent and can be enabled/disabled via `ENABLED` flag
   - `ENABLED` flag in each strategy class controls whether it runs
   - Allows testing multiple strategies with different universes simultaneously
   - Paper strategies use shared Alpaca account; live strategy uses separate account

2. **Retry Mechanism** - `@retry_on_exception` decorator in utils.py handles API failures
   - Default: 3 attempts with 1-second delays
   - Used on `get_signals()` and `get_positions()`
   - Raises exception after final attempt; calling code handles gracefully

3. **Timezone Handling** - `NY_TIMEZONE = pytz.timezone('America/New_York')` constant
   - Market schedule uses NY time, rebalance scheduled at 10:00 AM NY
   - InvestorManager also uses NY timezone for fee calculations

4. **Market Validation** - `MarketSchedule` class validates market hours before trading
   - Uses Alpaca clock API (`trading_client.get_clock()`)
   - Prevents accidental trades outside market hours

5. **State Persistence** - File-based flag system prevents duplicate rebalances
   - Path: `data/last_rebalance.txt`
   - Checked before each rebalance to ensure >22 trading days have elapsed
   - Single-line ISO date format survives bot restarts

6. **Paper Trading Default** - Safe mode for development/testing
   - All strategies configured with `PAPER=True` by default
   - Change to `PAPER=False` in strategy class only for live testing (high risk)

7. **Caching Strategy** - 24-hour cache for market data
   - Reduces API calls to yfinance
   - Cache file path: `data/cache.pkl`
   - Cache validity checked before each `load_market_data()` call

8. **Error Resilience** - Position close/open operations don't block rebalancing
   - Failed positions logged as warnings
   - Rebalancing completes even if some positions fail
   - Telegram admins notified of errors via logging handler

9. **Investor Fee System** - Tracks high watermarks and calculates performance fees
   - High watermark: Updated when portfolio reaches new peak
   - Fees charged on gains above high watermark
   - `is_fee_receiver` flag determines whether investor pays fees

## Data Flow

**Paper Trading (bot.py):**
1. Bot starts → Validates market schedule → Schedules 10:00 AM rebalancing
2. At rebalancing time:
   - Check if already rebalanced today (via RebalanceFlag)
   - If not, calculate days since last rebalance
   - If >22 trading days, trigger rebalance for each enabled strategy:
     - Download 1-year data for strategy's ticker universe
     - Calculate momentum scores and identify top 50
     - Close non-top-50 positions
     - Open top-50 positions with equal weight
     - Write new rebalance date to file

**Live Trading (LiveStrategy with InvestorManager):**
1. Strategy starts with investor manager
2. Before rebalancing:
   - Process pending investor operations (deposits, withdrawals, fees)
   - Allocate capital across low/medium/high sub-strategies per investor
3. Execute rebalancing per investor account
4. Calculate and record performance fees

## Data Directory Structure

- `last_rebalance.txt` - Tracks date of last rebalance (single line, ISO format)
- `cache.pkl` - 24-hour cache of market data (pickle format)
- `trading_bot.log` - Rotating log file with console + file output
- `investors_registry.csv` - Investor account registry (used by LiveStrategy only)
- `investors/{investor_name}/` - Per-investor data directory (pending ops, trades, portfolio state)
- `trades_history.csv` - Historical trade records for analysis
- `portfolio_performance.png` - Backtest results visualization

## Notable Implementation Details

- **Paper vs. Live Separation** - Paper strategies use default API credentials; live strategy uses `_LIVE` variants
- **Concurrent Tasks** - Telegram bot dispatcher (aiogram) runs async alongside APScheduler's background scheduler
- **Logging** - Dual output to console and `data/trading_bot.log` via `logging.basicConfig(handlers=[...])`
- **Position Tracking** - Uses Alpaca position API (`trading_client.get_all_positions()`), no local database
- **Backtesting** - Separate simulation module with `FakeAccount` and `FakePosition` classes

## Common Debugging Approaches

1. **Check API credentials:** Ensure `.env` has valid `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `TELEGRAM_BOT_TOKEN`
2. **Check strategy enablement:** Verify `ENABLED=True` in strategy class (located in `strategies/{strategy_name}.py`)
3. **Review logs:** Check `data/trading_bot.log` for detailed error messages with timestamps
4. **Test strategy in isolation:** Run `python backtest.py` to validate momentum calculations without trading
5. **Test with specific test file:** `pytest tests/test_strategy.py -v` to debug strategy issues
6. **Check market hours:** Verify trading time is within NYSE hours using `MarketSchedule.is_open_now()`
7. **Review rebalance flag:** Check `data/last_rebalance.txt` to see if rebalance was already executed
8. **Monitor Telegram:** Check admin chat for bot notifications to verify Telegram integration works
9. **Clear cache if stale:** Delete `data/cache.pkl` to force fresh data download from yfinance
10. **Investor issues:** For live strategy, check `investors_registry.csv` format and `data/investors/` directory structure
