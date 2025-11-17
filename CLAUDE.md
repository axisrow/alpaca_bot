# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Local Development
```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env  # Edit with your Alpaca API keys and Telegram token

# Run bot
python bot.py
```

### Testing
```bash
# Unit tests only (no real API calls required)
pytest -m "not integration"

# All tests including integration (requires valid API credentials)
pytest

# Single test file
pytest tests/test_alpaca_bot.py -k test_name

# With verbose output
pytest -v -m "not integration"
```

### Maintenance
```bash
# Clear cached market data (24-hour cache)
# Bot will re-download on next run
rm data/cache.pkl

# Build Docker image
docker build -t alpaca-bot .

# Run in Docker (mounts data/ directory for persistence)
docker run --env-file .env -v $(pwd)/data:/app/data alpaca-bot
```

## Architecture Overview

### Functional Programming Paradigm

The codebase uses **functional programming** throughout. This recent refactor (from OOP) emphasizes:

- **State Dictionaries**: All components use `create_*_state()` functions that return plain dicts
- **Pure Functions**: Functions take state as first param, return modified state or results
- **No Hidden Mutation**: Explicit data flow makes testing and debugging straightforward
- **Composition Over Inheritance**: Functions combined rather than classes extended

### Multi-Strategy Architecture

One bot instance manages **4 independent strategies simultaneously**:

1. **paper_low** - 10 positions (low-risk universe)
2. **paper_medium** - 20 positions (medium-risk universe)
3. **paper_high** - 50 positions (high-risk universe)
4. **live** - Variable positions (includes investor management)

Each strategy has:
- Isolated Alpaca account (separate API keys)
- Independent state dictionary
- Separate position tracking
- Own ticker universe configuration

The bot aggregates status/portfolio data across all 4 strategies.

### Async/Sync Bridge

- **Telegram bot** (handlers/, core/telegram_bot.py): Fully async with aiogram v3
- **Trading logic** (strategies/, core/): Synchronous (Alpaca SDK, pandas)
- **Scheduler**: Background APScheduler thread runs sync jobs
- **Sync context** (core/utils.py): Retry decorators and helpers

## Core Components & Data Flow

### Entry Point (bot.py)

The main orchestrator:

1. Creates trading bot state (initializes all 4 strategies)
2. Creates Telegram bot state (handlers, admin list)
3. Sets up logging (console + file + Telegram notifications)
4. Starts APScheduler (daily rebalance at 10:00 AM NY time)
5. Runs Telegram bot indefinitely

### Trading Bot State (core/alpaca_bot.py)

Central component managing strategy lifecycle:

**Key Functions:**
- `create_trading_bot_state()` - Initialize all strategies
- `execute_rebalance()` - Run rebalance across enabled strategies
- `get_portfolio_status()` - Aggregate positions/P&L from all strategies
- `get_rebalance_preview()` - Dry-run preview (no execution)

**Strategy Loading Pattern:**
```python
# Dynamically imports strategy modules at runtime
import strategies.paper_low as paper_low
import strategies.live as live

strategy_modules = {
    'paper_low': paper_low,
    'paper_medium': paper_medium,
    'paper_high': paper_high,
    'live': live,
}

# Creates isolated state for each enabled strategy
for strategy_name, module in strategy_modules.items():
    if module.ENABLED:
        strategy_state = create_strategy_state(module, ...)
        trading_bot_state['strategies'][strategy_name] = strategy_state
```

### Strategy System (strategies/)

All strategies implement the **momentum-based trading pattern**:

1. **get_signals()** - Calculate momentum `(last_price / first_price - 1)`, return top-N tickers
2. **close_positions()** - Close positions not in top-N
3. **open_positions()** - Open new positions for top-N
4. **rebalance()** - Orchestrate full rebalance (close → open)

**Base Strategy** (strategies/base.py):
- Momentum calculation with configurable lookback (default: "1y")
- Top-N position selection (strategy-specific)
- Equal-weight portfolio allocation
- Functional state management

**Live Strategy Differences** (strategies/live.py):
- Integrates investor management (deposits/withdrawals)
- Handles multi-account allocation (default: 45% low, 35% medium, 20% high)
- Performance fee calculations (high-water mark system)
- Only strategy that modifies investor operations

**Strategy Configuration** (module-level constants):
```python
API_KEY, SECRET_KEY      # Alpaca credentials
PAPER                    # Paper (True) or live (False) mode
TOP_COUNT                # Number of positions (10-50)
ENABLED                  # Enable/disable strategy
TICKERS                  # 'snp500_only' or 'all' universe
```

### Market Data Pipeline (core/data_loader.py)

Handles data loading with **intelligent caching**:

**Data Structure** (from yfinance):
- MultiIndex DataFrame: `Ticker` (level 0) → `Price` (level 1: Open/High/Low/Close/Volume)
- Access pattern: `df.xs('Close', level=0, axis=1)` gets close prices for all tickers

**Caching Architecture**:
- **Format**: Pickle (preserves MultiIndex structure)
- **Location**: `data/cache.pkl`
- **TTL**: 24 hours (configurable in config.py)
- **Update flow**: Check validity → use cache OR download with retry → save cache

**Data Sources** (combined):
- SNP500_TICKERS (503 large-cap)
- HIGH_TICKERS (1000+ small-cap, volatile)
- MEDIUM_TICKERS (3 quantum plays)
- CUSTOM_TICKERS (user-defined)

**See CACHE_FORMAT.md** for details on MultiIndex structure and common bugs.

### Investor Management (core/investor_manager.py)

Only used by the **live strategy**. Manages multi-account investor relationships:

**Data Storage** (CSV-based):
- `investors_registry.csv` - Investor metadata (name, email, allocation %)
- `data/investors/{name}/operations.csv` - Deposits/withdrawals
- `data/investors/{name}/trades.csv` - Executed trades
- `data/investors/{name}/snapshots/` - Daily balance history

**Key Concepts**:
- **Allocation Splits**: Investor funds split across 3 accounts by tier (45% low, 35% medium, 20% high)
- **Pending Operations**: Deposits/withdrawals queued until next rebalance
- **Performance Fees**: Calculated using high-water mark (charged only on gains)
- **Fee Receiver**: One investor designated to receive all collected fees

**Critical Flow**:
```python
# At rebalance time:
1. Process pending deposits (check_and_process_deposits)
2. Execute strategy trades
3. Calculate performance fees (check_and_calculate_fees)
4. Save daily snapshots (save_daily_snapshot)
```

### Telegram Integration (handlers/, core/telegram_bot.py)

Uses **aiogram v3** async framework. Command handlers split by user type:

**Admin Commands** (handlers/admins.py):
- `/check_rebalance` - Countdown to next rebalance + conditions
- `/test_rebalance` - Dry-run preview (no execution)
- `/clear` - Clear market data cache
- `/deposit <name> <amount> [account]` - Queue investor deposit
- `/withdraw <name> <amount> [account]` - Queue investor withdrawal
- `/balance_check` - Verify investor balance integrity
- `/investors` - Summary of all investors
- `/export <name>` - CSV export of investor trades/operations
- Text: "да"/"yes" or "нет"/"no" - Approve/reject rebalance (local mode only)

**User Commands** (handlers/users.py):
- `/status` - Portfolio summary, P&L across all strategies
- `/portfolio` - Detailed positions, holdings
- `/settings` - Bot configuration
- `/balance <name>` - Investor balance query

**Error Notifications** (core/telegram_logging.py):
- Errors logged to admin chat automatically
- Startup messages confirm bot health

**Access Control**:
- Admin commands check `message.from_user.id in ADMIN_IDS` (from config.py)
- User commands available to all

### Scheduling (APScheduler)

Two background jobs run daily:

**1. Rebalance Job** (10:00 AM NY time, Mon-Fri):
```python
perform_daily_task()
  → check_rebalance_conditions():
      - Has rebalanced today? (rebalance_flag.pkl)
      - Is market open?
      - Have 22+ trading days passed?
  → if local environment: request_rebalance_confirmation() via Telegram
  → else: execute_rebalance() directly
  → for each enabled strategy: strategy.rebalance()
  → write_flag() (mark today as done)
```

**2. Investor Snapshot Job** (4:30 PM NY time, daily):
- Save current balance for each investor across all 3 accounts

**Rebalance Interval**: 22 trading days (configurable: `REBALANCE_INTERVAL_DAYS` in config.py)

## Key Patterns & Conventions

### State Creation Pattern
```python
def create_component_state() -> Dict[str, Any]:
    return {
        'dependency1': initialize_dep1(),
        'dependency2': initialize_dep2(),
        'data': {},
        'config': {...},
    }

# Usage in other functions:
def my_function(component_state: Dict[str, Any]) -> Dict[str, Any]:
    component_state['data']['key'] = 'value'
    return component_state
```

### API Retry Decorator
```python
@retry_on_exception(retries=3, delay=2)
def risky_api_call():
    pass
```

### Environment-Aware Execution
```python
if ENVIRONMENT == "local":
    # Require human approval via Telegram before executing
    await request_rebalance_confirmation()
else:
    # Fully automated
    execute_rebalance()
```

### Strategy Module Access Pattern
```python
# Each strategy module exports these as module-level constants/functions:
API_KEY, SECRET_KEY  # Credentials
PAPER                # Paper trading flag
TOP_COUNT            # Position count
ENABLED              # Is strategy active?
TICKERS              # Ticker universe: 'snp500_only' or 'all'

def create_strategy_state(...): ...
def get_signals(...): ...
def rebalance(...): ...
```

## Configuration

### Required Environment Variables (.env)
```
TELEGRAM_BOT_TOKEN=<your_telegram_bot_token>
ALPACA_API_KEY_LOW=<paper_trading_key>
ALPACA_SECRET_KEY_LOW=<paper_trading_secret>
ALPACA_API_KEY_MEDIUM=<paper_trading_key>
ALPACA_SECRET_KEY_MEDIUM=<paper_trading_secret>
ALPACA_API_KEY_HIGH=<paper_trading_key>
ALPACA_SECRET_KEY_HIGH=<paper_trading_secret>
ALPACA_API_KEY_LIVE=<live_trading_key>
ALPACA_SECRET_KEY_LIVE=<live_trading_secret>
ENVIRONMENT=local  # or 'prod'
```

### Key Constants (config.py)
- `REBALANCE_INTERVAL_DAYS = 22` (trading days between rebalances)
- `CACHE_VALIDITY_HOURS = 24` (market data cache TTL)
- `MARKET_DATA_PERIOD = "1y"` (lookback for momentum calculation)
- `ADMIN_IDS = [123456789, ...]` (hardcoded Telegram admin IDs)
- `SNP500_TICKERS`, `MEDIUM_TICKERS`, `HIGH_TICKERS` (ticker universes)

### Strategy Enable/Disable
Toggle strategies on/off by setting `ENABLED = True/False` in each strategy module:
```python
# strategies/paper_low.py
ENABLED = True  # Turn off: ENABLED = False
```

## Critical Implementation Notes

### MultiIndex Data Structure
yfinance returns a MultiIndex DataFrame where:
- **Level 0 (Index)**: Ticker symbols (AAPL, GOOGL, MSFT, ...)
- **Level 1 (Columns)**: Price types (Open, High, Low, Close, Volume)

**Correct access pattern**:
```python
close_prices = df.xs('Close', level=0, axis=1)  # All tickers' close prices
```

See **CACHE_FORMAT.md** for common bugs when testing with mock data.

### Investor Multi-Account Model
A single investor's funds are split **across 3 strategy accounts**:

```
Investor "Alice" deposits $100,000
↓
45% → paper_low account
35% → paper_medium account
20% → paper_high account
```

At rebalance, each account trades independently. Daily snapshots aggregate balances.

### Pending Operations System
Deposits/withdrawals are **not executed immediately**. They:
1. Queue in `operations.csv` (pending state)
2. Execute at next rebalance
3. Funds become available after execution

This prevents mid-rebalance balance inconsistencies.

### Rebalance State Persistence
A `rebalance_flag.pkl` file tracks whether rebalancing has occurred today:
```python
write_flag()  # Record that rebalance executed
check_has_rebalanced_today()  # Prevent duplicate rebalances
```

This prevents multiple rebalances on the same day if scheduler runs multiple times.

## Git Workflow Notes

Recent commits show architectural evolution:
- `c4d62e2`: "Refactor: rewrite entire codebase from OOP to functional programming" - Major paradigm shift
- `514f353`: "test: update tests for functional architecture" - Test suite updated for new patterns

When modifying code, maintain functional patterns:
- No class-based state
- Pure functions with explicit parameters
- State dictionaries as the data structure
- Minimal side effects (I/O at boundaries)

## Testing Strategy

### Test Structure (tests/)
- **conftest.py**: Shared fixtures (mocked Alpaca clients, mock strategies)
- **Markers**: Use `@pytest.mark.integration` for tests requiring real API calls
- **Default run**: `pytest -m "not integration"` runs unit tests only

### Mocking Patterns
Test mocks should preserve MultiIndex structure for data:
```python
# Correct: MultiIndex with Ticker→Price hierarchy
mock_data = pd.DataFrame({
    ('AAPL', 'Close'): [100.0],
    ('GOOGL', 'Close'): [2000.0],
})
mock_data.columns = pd.MultiIndex.from_tuples(...)
```

## Production Deployment Checklist

1. Set `ENVIRONMENT=prod` in .env (enables auto-rebalance without approval)
2. Update all 4 Alpaca API key pairs in .env (NOT paper trading)
3. Update `ADMIN_IDS` in config.py with real Telegram admin IDs
4. Configure `TELEGRAM_BOT_TOKEN` from BotFather
5. Ensure `data/` directory persists across container restarts
6. Test `/status` command to verify all 4 strategies connected
7. Verify market hours (10:00 AM NY) for first rebalance
