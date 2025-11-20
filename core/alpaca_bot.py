from __future__ import annotations

"""Trading bot class for managing trading strategies."""
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from typing import Any, Callable, Dict, Tuple, Type

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from config import (ENVIRONMENT, SNP500_TICKERS, CUSTOM_TICKERS)
from .data_loader import get_snp500_tickers, load_market_data
from .investor_manager import InvestorManager
from .rebalance_flag import RebalanceFlag, NY_TIMEZONE
from .market_schedule import MarketSchedule
from .portfolio_manager import PortfolioManager
from .utils import run_sync
from .telegram_bot import TelegramBot


@dataclass(frozen=True)
class StrategyConfig:
    """Static configuration container for a strategy type."""

    name: str
    cls: Type[Any]
    extra_kwargs_factory: Callable[['TradingBot'], Dict[str, Any]] | None = None

class TradingBot:
    """Main trading bot class."""

    def __init__(self):
        """Initialize trading bot with multiple strategies."""
        load_dotenv()
        self.strategy_configs = self._build_strategy_configs()
        self.strategies: Dict[str, Dict[str, Any]] = {}
        self.investor_manager = None  # Will be set for LiveStrategy
        self._initialize_strategies()
        # Use first enabled strategy's trading_client for market schedule and portfolio manager
        first_enabled = next((data for _, data in self.iter_enabled_strategies()), None)
        if not first_enabled:
            logging.error("No enabled strategies configured!")
            sys.exit(1)
        first_client = first_enabled['client']
        self.market_schedule = MarketSchedule(first_client)
        self.portfolio_manager = PortfolioManager(
            trading_client=first_client,
            strategy=first_enabled.get('strategy')
        )
        self.rebalance_flag = RebalanceFlag()
        self.scheduler = BackgroundScheduler()
        self.telegram_bot = None  # Will be set after TelegramBot creation
        self.awaiting_rebalance_confirmation = False  # Flag for pending confirmation

    def _build_strategy_configs(self) -> Tuple[StrategyConfig, ...]:
        """Return immutable strategy configuration list."""
        from strategies.paper_low import PaperLowStrategy
        from strategies.paper_medium import PaperMediumStrategy
        from strategies.paper_high import PaperHighStrategy
        from strategies.live import LiveStrategy

        return (
            StrategyConfig("paper_low", PaperLowStrategy),
            StrategyConfig("paper_medium", PaperMediumStrategy),
            StrategyConfig("paper_high", PaperHighStrategy),
            StrategyConfig(
                "live",
                LiveStrategy,
                extra_kwargs_factory=lambda bot: {
                    "investor_manager": bot._ensure_investor_manager()
                }
            ),
        )

    def _ensure_investor_manager(self) -> InvestorManager:
        """Lazy-create InvestorManager instance."""
        if not self.investor_manager:
            self.investor_manager = InvestorManager(registry_path='investors_registry.csv')
            logging.info("InvestorManager initialized")
        return self.investor_manager

    @staticmethod
    def _calculate_total_close_value(positions_to_close: list, positions_dict: Dict[str, Any]) -> float:
        """Calculate total market value of positions to close.

        Args:
            positions_to_close: List of position symbols to close
            positions_dict: Dictionary of position objects keyed by symbol

        Returns:
            float: Total market value of positions to close
        """
        total_close_value = 0.0
        for symbol in positions_to_close:
            pos_info = positions_dict.get(symbol)
            if pos_info:
                market_value = float(getattr(pos_info, 'market_value', 0))
                total_close_value += market_value
        return total_close_value

    @staticmethod
    def _create_trading_client(api_key: str, secret_key: str, paper: bool) -> TradingClient:
        """Factory for TradingClient with correct URL."""
        url_override = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        return TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
            url_override=url_override
        )

    def _resolve_tickers(self, strategy_class: Any) -> list[str]:
        """Choose ticker universe based on strategy configuration."""
        if getattr(strategy_class, 'TICKERS', '') == 'snp500_only':
            # Maintain order while deduplicating
            combined = SNP500_TICKERS + CUSTOM_TICKERS
            return list(dict.fromkeys(combined))
        return get_snp500_tickers()

    def iter_enabled_strategies(self):
        """Yield (name, data) for enabled strategies only."""
        for name, data in self.strategies.items():
            if data.get('enabled'):
                yield name, data

    def _initialize_strategies(self) -> None:
        """Initialize all enabled trading strategies."""
        for config in self.strategy_configs:
            strategy_class = config.cls
            strategy_name = config.name
            if not strategy_class.ENABLED:
                logging.info("Strategy %s is disabled, skipping", strategy_name)
                continue

            try:
                api_key = getattr(strategy_class, 'API_KEY', '')
                secret_key = getattr(strategy_class, 'SECRET_KEY', '')
                paper = getattr(strategy_class, 'PAPER', True)

                if not all([api_key, secret_key]):
                    logging.error("Missing API keys for strategy %s", strategy_name)
                    continue

                trading_client = self._create_trading_client(api_key, secret_key, paper)
                tickers = self._resolve_tickers(strategy_class)
                extra_kwargs = config.extra_kwargs_factory(self) if config.extra_kwargs_factory else {}

                strategy = strategy_class(
                    trading_client=trading_client,
                    tickers=tickers,
                    top_count=strategy_class.TOP_COUNT,
                    **extra_kwargs,
                )

                self.strategies[strategy_name] = {
                    'client': trading_client,
                    'strategy': strategy,
                    'enabled': True,
                    'config': {
                        'paper': paper,
                        'top_count': strategy_class.TOP_COUNT
                    }
                }
                if strategy_name == 'live' and self.investor_manager:
                    self.strategies[strategy_name]['investor_manager'] = self.investor_manager

                logging.info("Strategy %s initialized successfully", strategy_name)

            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error initializing strategy %s: %s",
                    strategy_name,
                    exc,
                    exc_info=True
                )

    def set_telegram_bot(self, telegram_bot: TelegramBot) -> None:
        """Set reference to Telegram bot for notifications.

        Args:
            telegram_bot: TelegramBot instance
        """
        self.telegram_bot = telegram_bot

    def _check_rebalance_conditions(self) -> bool:
        """Check if rebalance conditions are met.

        Returns:
            bool: True if all conditions are met, False otherwise
        """
        if self.rebalance_flag.has_rebalanced_today():
            logging.info("Rebalancing already performed today.")
            return False

        is_open, reason = self.market_schedule.check_market_status()
        if not is_open:
            logging.info("Rebalancing postponed: %s", reason)
            return False

        # Check if 22 trading days have passed since last rebalance
        days_until = self.calculate_days_until_rebalance()
        if days_until > 0:
            logging.info("Rebalancing not required. Days remaining: %d", days_until)
            return False

        return True

    def execute_rebalance(self) -> None:
        """Execute portfolio rebalancing for all strategies."""
        try:
            logging.info("Performing portfolio rebalancing for all strategies...")
            errors: list[str] = []

            for strategy_name, strategy_data in self.iter_enabled_strategies():
                try:
                    logging.info("Rebalancing strategy: %s", strategy_name)
                    strategy_data['strategy'].rebalance()
                    logging.info("Strategy %s rebalanced successfully", strategy_name)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error(
                        "Error rebalancing %s: %s",
                        strategy_name,
                        exc,
                        exc_info=True
                    )
                    errors.append(f"{strategy_name}: {exc}")

            if errors:
                raise RuntimeError(
                    "One or more strategies failed to rebalance "
                    f"({'; '.join(errors)})"
                )

            self.rebalance_flag.write_flag()
            logging.info("All strategies rebalanced successfully")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Rebalance failed: %s", exc, exc_info=True)
            if self.telegram_bot:
                self.telegram_bot.send_error_notification_sync(
                    "Rebalancing Failed",
                    f"Error during portfolio rebalancing:\\n<code>{str(exc)}</code>"
                )
            raise

    def request_rebalance_confirmation_sync(self) -> None:
        """Request rebalance confirmation from admins (sync wrapper)."""
        if not self.telegram_bot:
            logging.warning("Telegram bot not available, executing rebalance directly")
            self.execute_rebalance()
            return

        try:
            run_sync(
                self.telegram_bot.send_rebalance_request(),
                loop=getattr(self.telegram_bot, 'loop', None),
                timeout=30
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error requesting rebalance confirmation: %s", exc)
            # Fallback: execute rebalance anyway
            logging.info("Executing rebalance as fallback")
            self.execute_rebalance()

    def perform_rebalance(self) -> None:
        """Perform portfolio rebalancing."""
        if not self._check_rebalance_conditions():
            return

        # In local environment, request confirmation; otherwise execute directly
        if ENVIRONMENT == "local":
            self.request_rebalance_confirmation_sync()
        else:
            self.execute_rebalance()

    def perform_daily_task(self) -> None:
        """Perform daily task: send countdown and rebalance if needed."""
        if self.telegram_bot:
            self.telegram_bot.send_daily_countdown_sync()
        self.perform_rebalance()

    def start(self) -> None:
        """Start the bot."""
        logging.info("=== Starting trading bot ===")
        is_open, reason = self.market_schedule.check_market_status()
        now_ny = datetime.now(NY_TIMEZONE)
        logging.info("Current time (NY): %s", now_ny.strftime('%Y-%m-%d %H:%M:%S %Z'))
        logging.info("Market status: %s%s",
                     'open' if is_open else 'closed',
                     f" (Reason: {reason})" if not is_open else "")

        # Pre-load SNP500 + HIGH_TICKERS for all strategies to use cache
        try:
            logging.info("Pre-loading market data for all strategies...")
            load_market_data()
            logging.info("Market data pre-loaded successfully")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error pre-loading market data: %s", exc, exc_info=True)

        if not self.scheduler.running:
            self.scheduler.start()
            self.scheduler.add_job(
                self.perform_daily_task,
                'cron',
                day_of_week='mon-fri',
                hour=10,
                minute=0,
                timezone=NY_TIMEZONE
            )
            # Add daily snapshot job for investors (after market close)
            if self.investor_manager:
                self.scheduler.add_job(
                    self.save_daily_investor_snapshots,
                    'cron',
                    hour=16,
                    minute=30,
                    timezone=NY_TIMEZONE,
                    id='daily_investor_snapshots'
                )
                logging.info("Daily investor snapshot job scheduled")
                # Hourly balance integrity check with admin alert
                self.scheduler.add_job(
                    self.check_balance_integrity_job,
                    'interval',
                    hours=1,
                    id='balance_integrity_watchdog'
                )
                logging.info("Balance integrity watchdog scheduled (hourly)")
        else:
            logging.info("Scheduler already running")
        if is_open:
            logging.info("Starting initial rebalancing...")
            self.perform_rebalance()

    def stop(self) -> None:
        """Stop scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logging.info("Scheduler stopped")

    def save_daily_investor_snapshots(self) -> None:
        """Save daily investor account snapshots."""
        try:
            if self.investor_manager:
                now_ny = datetime.now(NY_TIMEZONE)
                self.investor_manager.save_daily_snapshot(now_ny)
                logging.info("Daily investor snapshots saved")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error saving investor snapshots: %s", exc)

    def check_balance_integrity_job(self) -> None:
        """Verify balance integrity and alert admins hourly if mismatch."""
        try:
            if not self.investor_manager:
                return
            live_strategy = self.strategies.get('live')
            if not live_strategy:
                logging.warning("Balance watchdog skipped: live strategy not available")
                return
            trading_client = live_strategy['client']
            is_valid, msg = self.investor_manager.verify_balance_integrity(trading_client)
            if not is_valid:
                logging.error("Balance integrity watchdog detected mismatch: %s", msg)
                if self.telegram_bot:
                    self.telegram_bot.send_error_notification_sync(
                        "Balance integrity mismatch",
                        msg,
                        is_warning=False
                    )
            else:
                logging.info("Balance integrity watchdog OK: %s", msg)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Balance integrity watchdog failed: %s", exc, exc_info=True)

    def get_portfolio_status(self) -> Tuple[Dict[str, Dict[str, Any]], float, float]:
        """Get detailed portfolio data from all strategies.

        Returns:
            Tuple: (positions_by_strategy, total_portfolio_value, total_pnl)
        """
        try:
            positions_by_strategy = {}
            total_portfolio_value = 0.0
            total_pnl = 0.0

            for strategy_name, strategy_data in self.iter_enabled_strategies():
                try:
                    client = strategy_data['client']

                    # Get positions
                    all_positions = client.get_all_positions()
                    positions = {pos.symbol: float(pos.qty) for pos in all_positions}

                    # Get account
                    account = client.get_account()
                    portfolio_value = float(getattr(account, 'portfolio_value', 0))

                    # Calculate P&L
                    pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in all_positions)

                    positions_by_strategy[strategy_name] = {
                        'positions': positions,
                        'portfolio_value': portfolio_value,
                        'pnl': pnl,
                        'all_positions': {p.symbol: p for p in all_positions}
                    }

                    total_portfolio_value += portfolio_value
                    total_pnl += pnl

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("Error retrieving data for %s: %s", strategy_name, exc)
                    positions_by_strategy[strategy_name] = {
                        'positions': {},
                        'portfolio_value': 0.0,
                        'pnl': 0.0,
                        'all_positions': {}
                    }

            return positions_by_strategy, total_portfolio_value, total_pnl

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving portfolio data: %s", exc)
            return {}, 0.0, 0.0

    def get_trading_stats(self) -> Dict[str, float]:
        """Get real trading statistics from all strategies.

        Returns:
            Dict[str, float]: Aggregated trading statistics
        """
        try:
            total_trades_today = 0
            total_pnl = 0.0

            today = datetime.now(NY_TIMEZONE).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            for strategy_name, strategy_data in self.iter_enabled_strategies():
                try:
                    client = strategy_data['client']

                    # Get trades for today
                    request = GetOrdersRequest(
                        status=QueryOrderStatus.CLOSED,
                        after=today
                    )
                    trades = client.get_orders(filter=request)
                    total_trades_today += len(trades)

                    # Calculate P&L
                    positions = client.get_all_positions()
                    pnl = sum(float(getattr(pos, 'unrealized_pl', 0)) for pos in positions)
                    total_pnl += pnl

                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("Error retrieving stats for %s: %s", strategy_name, exc)

            return {
                "trades_today": total_trades_today,
                "pnl": total_pnl,
                "win_rate": 0.0  # Simplified version, win_rate requires history analysis
            }
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Error retrieving trading statistics: %s", exc)
            return {"trades_today": 0, "pnl": 0.0, "win_rate": 0.0}

    def get_settings(self) -> Dict[str, Any]:
        """Get bot settings.

        Returns:
            Dict[str, Any]: Settings dictionary with all strategies
        """
        strategies_info = {}

        for strategy_name, strategy_data in self.iter_enabled_strategies():
            config = strategy_data['config']
            strategies_info[strategy_name] = {
                'positions_count': config.get('top_count', 10),
                'mode': 'Paper Trading' if config.get('paper', True) else 'Live Trading',
                'enabled': True
            }

        return {
            "rebalance_time": "10:00 NY",
            "strategies": strategies_info
        }

    def calculate_days_until_rebalance(self) -> int:
        """Calculate trading days until rebalancing.

        Returns:
            int: Remaining trading days (0 if time to rebalance)
        """
        from config import REBALANCE_INTERVAL_DAYS

        last_date = self.rebalance_flag.get_last_rebalance_date()
        if last_date is None:
            return 0  # Time to rebalance if never done before

        today = datetime.now(NY_TIMEZONE)
        trading_days_passed = self.market_schedule.count_trading_days(last_date, today)

        return max(0, REBALANCE_INTERVAL_DAYS - trading_days_passed)

    def get_next_rebalance_date(self) -> datetime:
        """Get the exact date of next rebalancing.

        Returns:
            datetime: Next rebalance date in NY timezone
        """
        from config import REBALANCE_INTERVAL_DAYS

        last_date = self.rebalance_flag.get_last_rebalance_date()
        if last_date is None:
            # If never rebalanced, next rebalance is today
            return datetime.now(NY_TIMEZONE)

        # Start from the last rebalance date and count forward 22 trading days
        current = last_date.date()
        trading_days = (
            current + timedelta(days=i)
            for i in range(1, 365)
            if (current + timedelta(days=i)).weekday() < 5
        )
        next_date = next(
            d for idx, d in enumerate(trading_days)
            if idx == REBALANCE_INTERVAL_DAYS - 1
        )

        return NY_TIMEZONE.localize(datetime.combine(next_date, dt_time(10, 0)))

    def get_rebalance_preview(self) -> Dict[str, Dict[str, Any]]:
        """Get a preview of what would happen in rebalancing (dry-run) for all strategies.

        Returns:
            Dict[str, Dict]: Rebalance plan for each strategy
        """
        previews = {}

        for strategy_name, strategy_data in self.iter_enabled_strategies():
            client = strategy_data['client']
            strategy = strategy_data['strategy']

            try:
                # Get current positions
                all_positions = client.get_all_positions()
                current_positions = {pos.symbol: float(pos.qty) for pos in all_positions}
                positions_dict = {p.symbol: p for p in all_positions}

                # Get account
                account = client.get_account()
                available_cash = float(getattr(account, 'cash', 0))
                portfolio_value = float(
                    getattr(
                        account,
                        'portfolio_value',
                        getattr(account, 'equity', 0.0)
                    )
                )

                # Get top N by momentum
                top_tickers = strategy.get_signals()

                # Calculate what would change
                top_set = set(top_tickers)
                positions_to_close = list(set(current_positions.keys()) - top_set)
                positions_to_open = list(top_set - set(current_positions.keys()))

                # Target equal-weight value per ticker
                target_position_value = (
                    portfolio_value / len(top_tickers)
                    if top_tickers else 0.0
                )
                rebalance_plan: Dict[str, Dict[str, float]] = {}
                if target_position_value > 0:
                    for ticker in top_tickers:
                        pos_info = positions_dict.get(ticker)
                        current_value = float(getattr(pos_info, 'market_value', 0)) if pos_info else 0.0
                        rebalance_plan[ticker] = {
                            "current_value": current_value,
                            "target_value": target_position_value,
                            "difference": target_position_value - current_value
                        }

                previews[strategy_name] = {
                    "current_positions": current_positions,
                    "positions_dict": positions_dict,
                    "top_tickers": top_tickers,
                    "top_count": strategy_data['config'].get('top_count', 10),
                    "positions_to_close": positions_to_close,
                    "positions_to_open": positions_to_open,
                    "available_cash": available_cash,
                    "portfolio_value": portfolio_value,
                    "target_position_value": target_position_value,
                    "rebalance_plan": rebalance_plan
                }

            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error("Error previewing rebalance for %s: %s", strategy_name, exc)
                previews[strategy_name] = {
                    "error": str(exc),
                    "current_positions": {},
                    "positions_dict": {},
                    "top_tickers": [],
                    "top_count": strategy_data['config'].get('top_count', 10),
                    "positions_to_close": [],
                    "positions_to_open": [],
                    "available_cash": 0.0,
                    "portfolio_value": 0.0,
                    "target_position_value": 0.0,
                    "rebalance_plan": {}
                }

        return previews

    def build_rebalance_summary(self, previews: Dict[str, Dict[str, Any]]) -> str:
        """Build formatted summary for rebalance previews."""
        sections: list[str] = []
        for strategy_name, preview in previews.items():
            section = [f"<b>🔹 {strategy_name.upper()}</b>"]

            if "error" in preview:
                section.append(f"  ❌ Error: {preview['error']}")
                sections.append("\n".join(section))
                continue

            positions_dict = preview.get("positions_dict", {})
            positions_to_close = preview.get("positions_to_close", [])
            positions_to_open = preview.get("positions_to_open", [])
            available_cash = float(preview.get("available_cash", 0.0))
            portfolio_value = float(preview.get("portfolio_value", 0.0))
            target_value = float(preview.get("target_position_value", 0.0))
            top_tickers = preview.get("top_tickers", [])
            rebalance_plan = preview.get("rebalance_plan", {})

            total_close_value = self._calculate_total_close_value(positions_to_close, positions_dict)
            open_value = len(top_tickers) * target_value if target_value else 0.0
            section.append(f"  📊 Basket size: {len(top_tickers)} tickers")
            section.append(f"  💼 Portfolio: ${portfolio_value:.2f}")
            section.append(f"  💰 Cash: ${available_cash:.2f}")
            if target_value:
                section.append(f"  🎯 Target per ticker: ${target_value:.2f}")
            section.append(
                f"  📉 Close: {len(positions_to_close)} (${total_close_value:.2f})"
            )
            section.append(
                f"  📈 Open: {len(positions_to_open)} (target spend ${open_value:.2f})"
            )

            if isinstance(rebalance_plan, dict) and rebalance_plan:
                increase = sum(
                    1 for data in rebalance_plan.values()
                    if isinstance(data, dict) and data.get("difference", 0) > 1
                )
                decrease = sum(
                    1 for data in rebalance_plan.values()
                    if isinstance(data, dict) and data.get("difference", 0) < -1
                )
                section.append(f"  🔧 Adjustments: {increase} buy / {decrease} sell")

            sections.append("\n".join(section))

        return "\n\n".join(sections)
