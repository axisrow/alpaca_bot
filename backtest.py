"""Module for backtesting trading strategy."""
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from alpaca.trading.enums import OrderSide

from config import snp500_tickers
from strategy import MomentumStrategy

# =======================
# BACKTEST SETTINGS
# =======================
INITIAL_CASH = 100000.0
START_DATE = datetime(2025, 3, 1)
END_DATE = datetime(2025, 3, 3)
# Rebalancing by day (can be changed to 'M' for monthly, etc.)
REBALANCING_FREQUENCY = 'D'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


class FakePosition:
    """Fake position for simulation."""

    def __init__(self, symbol: str, qty: float):
        """Initialize position.

        Args:
            symbol: Ticker
            qty: Number of shares
        """
        self.symbol = symbol
        self.qty = qty


class FakeAccount:
    """Fake account for simulation."""

    def __init__(self, cash: float):
        """Initialize account.

        Args:
            cash: Available cash
        """
        self.cash = cash


class FakeTradingClient:
    """Fake trading client for simulation."""

    def __init__(self, initial_cash: float, prices: pd.DataFrame):
        """Initialize client.

        Args:
            initial_cash: Initial capital
            prices: DataFrame with historical prices
        """
        self.cash = initial_cash
        self.positions: Dict[str, float] = {}
        self.prices = prices
        self.current_date = None
        self.trade_history: List[Dict] = []

    def set_current_date(self, date: pd.Timestamp) -> None:
        """Set current date for simulation.

        Args:
            date: Date to set
        """
        self.current_date = date

    def get_price(self, ticker: str) -> float:
        """Get price for ticker on current date.

        Args:
            ticker: Ticker

        Returns:
            float: Stock price
        """
        try:
            price = self.prices[ticker].reindex(
                [self.current_date],
                method='nearest'
            ).iloc[0]
            return float(price)
        except Exception as exc:
            raise ValueError(
                f"Failed to get price for {ticker} "
                f"on {self.current_date}"
            ) from exc

    def get_all_positions(self) -> List[FakePosition]:
        """Get all positions.

        Returns:
            List[FakePosition]: List of positions
        """
        return [FakePosition(ticker, qty)
                for ticker, qty in self.positions.items()]

    def get_account(self) -> FakeAccount:
        """Get account information.

        Returns:
            FakeAccount: Account information
        """
        return FakeAccount(self.cash)

    def close_position(self, ticker: str) -> None:
        """Close position.

        Args:
            ticker: Ticker to close
        """
        if ticker not in self.positions:
            raise ValueError(f"No position for {ticker}")
        price = self.get_price(ticker)
        qty = self.positions[ticker]
        proceeds = qty * price
        self.cash += proceeds
        logging.info(
            "Fake client: Sold position %s (%s shares at $%.2f), "
            "proceeds $%.2f",
            ticker,
            qty,
            price,
            proceeds
        )
        # Record sell transaction
        self.trade_history.append({
            'date': self.current_date,
            'symbol': ticker,
            'side': 'SELL',
            'shares': qty,
            'price': price,
            'total': proceeds
        })
        del self.positions[ticker]

    def submit_order(self, order) -> None:
        """Submit order for execution.

        Args:
            order: Order to execute
        """
        if order.side == OrderSide.BUY:
            price = self.get_price(order.symbol)
            shares = int(order.notional // price)
            if shares <= 0:
                raise ValueError(
                    f"Insufficient funds to buy at least 1 share "
                    f"of {order.symbol}"
                )
            cost = shares * price
            if cost > self.cash:
                raise ValueError(
                    f"Insufficient cash to buy {order.symbol}"
                )
            self.cash -= cost
            self.positions[order.symbol] = (
                self.positions.get(order.symbol, 0) + shares
            )
            logging.info(
                "Fake client: Bought %s shares of %s at $%.2f, "
                "cost $%.2f",
                shares,
                order.symbol,
                price,
                cost
            )
            # Record buy transaction
            self.trade_history.append({
                'date': self.current_date,
                'symbol': order.symbol,
                'side': 'BUY',
                'shares': shares,
                'price': price,
                'total': cost
            })
        else:
            raise NotImplementedError("Only buy orders are supported")


class BacktestMomentumStrategy(MomentumStrategy):
    """Strategy subclass for backtesting with historical data."""

    def __init__(
        self,
        trading_client,
        tickers: List[str],
        prices: pd.DataFrame,
        current_date: pd.Timestamp
    ):
        """Initialize strategy for backtesting.

        Args:
            trading_client: Trading client
            tickers: List of tickers
            prices: DataFrame with historical prices
            current_date: Current date for simulation
        """
        super().__init__(trading_client, tickers)
        self.prices = prices
        self.current_date = current_date

    def get_signals(self) -> List[str]:
        """Get signals based on historical data.

        Returns:
            List[str]: List of tickers with highest momentum
        """
        one_year_ago = self.current_date - timedelta(days=365)
        try:
            price_start = self.prices.reindex(
                [one_year_ago],
                method='nearest'
            ).iloc[0]
            price_end = self.prices.reindex(
                [self.current_date],
                method='nearest'
            ).iloc[0]
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Error getting prices for momentum calculation on %s: %s",
                self.current_date,
                exc
            )
            return []
        momentum = (price_end / price_start - 1).nlargest(10)
        return momentum.index.tolist()


def main() -> None:  # pylint: disable=too-many-locals,too-many-statements
    """Main backtesting function."""
    # ---------------------------
    # LOAD AND PREPARE DATA
    # ---------------------------
    data_start = START_DATE - timedelta(days=370)
    logging.info("Loading historical data from yfinance...")
    data = yf.download(snp500_tickers,
                       start=data_start.strftime("%Y-%m-%d"),
                       end=END_DATE.strftime("%Y-%m-%d"),
                       group_by='ticker',
                       progress=False)

    # Extract 'Close' data for each ticker
    close_data = {}
    for ticker in snp500_tickers:
        try:
            ticker_df = data[ticker]
            if 'Close' in ticker_df.columns:
                close_data[ticker] = ticker_df['Close']
            else:
                logging.warning("No 'Close' data for %s", ticker)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning("Error loading data for %s: %s", ticker, exc)

    prices = pd.DataFrame(close_data)
    if prices.empty:
        logging.error("Failed to load data for any ticker.")
        return
    prices.sort_index(inplace=True)
    prices.index = pd.to_datetime(prices.index)

    available_tickers = list(prices.columns)
    if not available_tickers:
        logging.error("No available tickers for backtesting.")
        return

    trading_dates = prices.index
    rebalancing_dates = (
        trading_dates[trading_dates >= START_DATE]
        .to_series()
        .resample(REBALANCING_FREQUENCY)
        .last()
        .dropna()
    )

    # ---------------------------
    # INITIALIZE CLIENT, STRATEGY AND TRANSACTION LOGGING
    # ---------------------------
    fake_client = FakeTradingClient(INITIAL_CASH, prices)
    strategy = BacktestMomentumStrategy(
        fake_client,
        available_tickers,
        prices,
        current_date=rebalancing_dates.index[0]
    )
    portfolio_history: List[Dict] = []

    # ---------------------------
    # BACKTEST LOOP
    # ---------------------------
    for current_date in rebalancing_dates.index:
        logging.info("\n--- Rebalancing on %s ---", current_date.date())
        fake_client.set_current_date(current_date)
        strategy.current_date = current_date

        try:
            strategy.rebalance()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Error during rebalancing on %s: %s",
                current_date.date(),
                exc
            )

        # Calculate portfolio value for current date
        total_value = fake_client.cash
        for ticker, qty in fake_client.positions.items():
            try:
                price = fake_client.get_price(ticker)
                total_value += qty * price
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.warning(
                    "Failed to get price for %s on %s: %s",
                    ticker,
                    current_date.date(),
                    exc
                )
        logging.info(
            "Portfolio value on %s: $%.2f",
            current_date.date(),
            total_value
        )
        portfolio_history.append({
            'date': current_date,
            'portfolio_value': total_value
        })

    # Final portfolio valuation
    final_date = rebalancing_dates.index[-1]
    final_value = fake_client.cash
    for ticker, qty in fake_client.positions.items():
        try:
            price = fake_client.get_price(ticker)
            final_value += qty * price
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Failed to get price for %s on %s: %s",
                ticker,
                final_date.date(),
                exc
            )
    logging.info(
        "\nFinal portfolio value on %s: $%.2f",
        final_date.date(),
        final_value
    )

    # ---------------------------
    # VISUALIZE PORTFOLIO RETURNS
    # ---------------------------
    portfolio_df = pd.DataFrame(portfolio_history)
    portfolio_df.set_index('date', inplace=True)
    plt.figure(figsize=(10, 6))
    plt.plot(portfolio_df.index, portfolio_df['portfolio_value'], marker='o')
    plt.title("Portfolio Performance")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value ($)")
    plt.grid(True)
    plt.savefig("data/portfolio_performance.png")
    plt.show()
    logging.info("Portfolio performance chart saved as portfolio_performance.png")

    # ---------------------------
    # SAVE TRADE HISTORY TO CSV
    # ---------------------------
    trades_df = pd.DataFrame(fake_client.trade_history)
    trades_df.to_csv("data/trades_history.csv", index=False)
    logging.info("Trade history saved to data/trades_history.csv")


if __name__ == "__main__":
    main()
