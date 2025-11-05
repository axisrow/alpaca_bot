"""Data loading and caching module for market data."""
import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from config import ENVIRONMENT

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data")
CACHE_FILE = CACHE_DIR / "cache.pkl"
CACHE_VALIDITY_HOURS = 24


class DataLoader:
    """Handles loading and caching of market data."""

    @staticmethod
    def load_market_data(
        tickers: list,
        period: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        group_by: Optional[str] = None,
        telegram_bot: Optional[Any] = None,
    ) -> pd.DataFrame:
        """
        Load market data from cache or yfinance.

        Args:
            tickers: List of stock tickers
            period: Period string (e.g., "1y") - ignored if start/end provided
            start: Start date string (e.g., "2023-01-01")
            end: End date string (e.g., "2024-01-01")
            group_by: How to group the data ("ticker" or None)

        Returns:
            DataFrame with market data
        """
        # Create cache directory if it doesn't exist
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Check if we can use cache
        if DataLoader._is_cache_valid():
            logger.info("Loading data from cache")
            return DataLoader._load_from_cache()

        # Show progress only in local environment
        show_progress = ENVIRONMENT == "local"

        logger.info(f"Loading data from yfinance (progress={'enabled' if show_progress else 'disabled'})")

        # Prepare download parameters
        download_kwargs: dict[str, Any] = {"progress": show_progress}

        if period:
            download_kwargs["period"] = period
        if start:
            download_kwargs["start"] = start
        if end:
            download_kwargs["end"] = end
        if group_by:
            download_kwargs["group_by"] = group_by

        # Explicitly set auto_adjust to avoid FutureWarning
        download_kwargs["auto_adjust"] = True

        # Download data
        try:
            data = yf.download(tickers, **download_kwargs)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Failed to download market data: %s", exc, exc_info=True)
            # Extract failed tickers from error message if possible
            error_str = str(exc)
            if "Failed downloads:" in error_str:
                logger.warning("Partial download failure: %s", error_str)
            raise

        if data is None or data.empty:
            logger.error("Failed to download market data")
            raise ValueError("No data downloaded from yfinance")

        # Check for tickers with missing data (after successful download)
        if isinstance(data, pd.DataFrame) and 'Close' in data.columns:
            missing_tickers = []
            if isinstance(data['Close'], pd.DataFrame):
                # Multiple tickers case
                for ticker in tickers:
                    if ticker not in data['Close'].columns or data['Close'][ticker].isna().all():
                        missing_tickers.append(ticker)
            if missing_tickers:
                error_msg = f"Data missing for tickers (may be delisted): {missing_tickers}"
                logger.warning(error_msg)
                if telegram_bot:
                    telegram_bot.send_error_notification_sync(
                        "Data Quality Warning",
                        f"<code>{error_msg}</code>",
                        is_warning=True
                    )

        # Save to cache
        DataLoader._save_to_cache(data)
        logger.info("Data cached successfully")

        return data

    @staticmethod
    def _get_cache_path() -> Path:
        """Get the path to the cache file."""
        return CACHE_FILE

    @staticmethod
    def _is_cache_valid() -> bool:
        """Check if cache exists and is valid (less than 24 hours old)."""
        cache_path = DataLoader._get_cache_path()

        if not cache_path.exists():
            return False

        # Check file modification time
        file_mtime = os.path.getmtime(cache_path)
        file_age = datetime.now() - datetime.fromtimestamp(file_mtime)

        is_valid = file_age < timedelta(hours=CACHE_VALIDITY_HOURS)

        if is_valid:
            logger.debug(f"Cache is valid (age: {file_age})")
        else:
            logger.debug(f"Cache is expired (age: {file_age})")

        return is_valid

    @staticmethod
    def _load_from_cache() -> pd.DataFrame:
        """Load data from cache file."""
        cache_path = DataLoader._get_cache_path()

        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)
            logger.info(f"Loaded {len(data)} rows from cache")
            return data
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            raise

    @staticmethod
    def _save_to_cache(data: pd.DataFrame) -> None:
        """Save data to cache file."""
        cache_path = DataLoader._get_cache_path()

        try:
            with open(cache_path, "wb") as f:
                pickle.dump(data, f)
            logger.debug(f"Data cached to {cache_path}")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")
            raise

    @staticmethod
    def clear_cache() -> None:
        """Clear the cache file."""
        cache_path = DataLoader._get_cache_path()

        if cache_path.exists():
            cache_path.unlink()
            logger.info("Cache cleared")
        else:
            logger.info("Cache file does not exist")
