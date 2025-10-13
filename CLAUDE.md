# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an automated trading bot that combines Alpaca Markets API trading with a Telegram interface. The bot implements a momentum-based trading strategy that rebalances a portfolio daily by selecting the top 10 S&P 500 stocks with the highest 1-year momentum returns.

## Key Architecture

### Core Components

- **main.py**: Entry point that orchestrates both the trading bot and Telegram bot
  - `TradingBot`: Manages Alpaca trading client, market schedule, portfolio management, and APScheduler for daily rebalancing
  - `TelegramBot`: Manages aiogram bot for user interaction
  - Runs both components concurrently using asyncio

- **strategy.py**: Contains `MomentumStrategy` class
  - Uses yfinance to download 1-year historical data for S&P 500 tickers
  - Calculates momentum returns and selects top 10 stocks
  - Handles portfolio rebalancing (closing old positions, opening new ones)

- **backtest.py**: Backtesting framework with `BacktestMomentumStrategy`
  - Creates fake trading client (`FakeTradingClient`) to simulate trades
  - Generates portfolio performance charts and trade history CSV
  - Extends the main strategy to work with historical data

- **handlers.py**: Defines Telegram bot command and callback handlers
  - Portfolio status, trading statistics, settings display
  - Uses router pattern with dependency injection of `TradingBot` instance

- **keyboards.py**: Telegram bot keyboard layouts (ReplyKeyboard and InlineKeyboard)

- **config.py**: Configuration and constants
  - Full S&P 500 ticker list
  - Environment variable loading for Telegram token

### Key Design Patterns

- **Market Schedule Management**: `MarketSchedule` class handles NY timezone conversions and market open/close checks
- **Rebalance Flag**: Prevents duplicate rebalancing on same day via `data/last_rebalance.txt`
- **Retry Decorator**: `@retry_on_exception()` decorator for handling transient API failures
- **Dual-Mode Operation**: Trading bot runs on APScheduler (cron: Mon-Fri 10:00 AM NY), Telegram bot runs async polling

## Environment Variables

Required in `.env` file (not committed to git):
- `ALPACA_API_KEY`: Alpaca Markets API key
- `ALPACA_SECRET_KEY`: Alpaca Markets secret key
- `TELEGRAM_BOT_TOKEN`: Telegram bot token

## Development Commands

### Running the Bot
```bash
python main.py
```
This starts both the trading bot (with scheduled rebalancing) and Telegram bot interface.

### Running Backtest
```bash
python backtest.py
```
Edit constants at top of `backtest.py` to configure:
- `INITIAL_CASH`: Starting capital
- `START_DATE` / `END_DATE`: Backtest period
- `REBALANCING_FREQUENCY`: 'D' (daily), 'M' (monthly), etc.

Results saved to:
- `data/portfolio_performance.png`: Chart of portfolio value over time
- `data/trades_history.csv`: All simulated trades

### Dependencies
```bash
pip install -r requirements.txt
```

### Docker
```bash
docker build -t alpaca_bot .
docker run --env-file .env alpaca_bot
```

## Trading Strategy Details

1. **Signal Generation**: Downloads 1-year historical close prices for all S&P 500 tickers, calculates period returns, selects top 10
2. **Position Sizing**: Equal-weighted allocation of available cash across selected stocks
3. **Rebalancing**: Closes positions not in top 10, opens new positions with available cash
4. **Execution**: Market orders via Alpaca Trading API (paper trading mode by default)

## Data Files

The `data/` directory (gitignored) contains:
- `last_rebalance.txt`: Date of last successful rebalance
- `trading_bot.log`: Application logs
- `portfolio_performance.png`: Backtest performance chart
- `trades_history.csv`: Backtest trade records

## Important Notes

- Bot operates in **paper trading mode** by default (see main.py:164, 176)
- Market hours are 9:30 AM - 4:00 PM NY time
- Scheduled rebalancing at 10:00 AM NY time on weekdays
- If market is open when bot starts, immediate rebalancing is triggered
- yfinance download timeout is 30 seconds (strategy.py:38)
