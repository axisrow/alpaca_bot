"""Data loading and caching module for market data."""
import logging
import os
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

import pandas as pd
import yfinance as yf

from config import ENVIRONMENT, SNP500_TICKERS, HIGH_TICKERS, CUSTOM_TICKERS

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data")
CACHE_FILE = CACHE_DIR / "cache.pkl"
CACHE_VALIDITY_HOURS = 24


class DataLoader:
    """Handles loading and caching of market data."""

    failed_tickers: list[str] = []  # Track tickers that fail to download

    @staticmethod
    def load_market_data(
        period: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Load market data (SNP500 + HIGH_TICKERS + CUSTOM_TICKERS) from cache or yfinance.

        Args:
            period: Period string (e.g., "1y") - ignored if start/end provided
            start: Start date string (e.g., "2023-01-01")
            end: End date string (e.g., "2024-01-01")
            group_by: How to group the data ("ticker" or None)

        Returns:
            DataFrame with market data for all tickers (SNP500 + HIGH + CUSTOM)
        """
        # Create cache directory if it doesn't exist
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Check if we can use cache
        if DataLoader._is_cache_valid():
            logger.info("Loading data from cache")
            return DataLoader._load_from_cache()

        logger.info("Loading data from yfinance")

        # Always load SNP500 + HIGH_TICKERS + CUSTOM_TICKERS
        tickers = list(set(SNP500_TICKERS + HIGH_TICKERS + CUSTOM_TICKERS))

        # Prepare download parameters
        download_kwargs: dict[str, Any] = {"progress": ENVIRONMENT == "local"}

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
        # Group by ticker for cleaner multi-index columns
        download_kwargs["group_by"] = "ticker"

        # Download data with retry mechanism for timeout errors
        max_retries = 3
        retry_delay = 2
        data = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Downloading market data (attempt {attempt}/{max_retries})")
                data = yf.download(tickers, **download_kwargs)
                break
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if attempt < max_retries:
                    logger.warning(f"Attempt {attempt} failed: {exc}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to download market data after %d attempts: %s", max_retries, exc, exc_info=True)
                    raise

        if data is None or data.empty:
            logger.error("Failed to download market data")
            raise ValueError("No data downloaded from yfinance")

        # Validate MultiIndex structure: should have 'Close' in Level 0 (Price level)
        if 'Close' not in data.columns.get_level_values(1):
            logger.error("'Close' column not found in downloaded data")
            raise ValueError("'Close' column not found in data")

        # Detect failed tickers (those with no Close price data)
        expected = set(tickers)
        # With group_by='ticker', columns are MultiIndex: ('Close', 'AAPL'), ('Close', 'GOOGL'), etc.
        if 'Close' in data.columns.get_level_values(0):
            # Get tickers that have Close data
            downloaded = set(data['Close'].columns)
        else:
            # Fallback: no Close column found
            downloaded = set()

        failed = list(expected - downloaded)
        if failed:
            DataLoader.failed_tickers = failed
            logger.warning(
                "Failed to download %d/%d tickers: %s",
                len(failed),
                len(expected),
                failed[:20] if len(failed) > 20 else failed
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

    @staticmethod
    def get_snp500_tickers() -> list[str]:
        """Get SNP500_TICKERS + HIGH_TICKERS + CUSTOM_TICKERS as universal source for all strategies.

        Returns:
            List of SNP500 + HIGH + CUSTOM tickers for universal data loading
        """
        combined = list(set(SNP500_TICKERS + HIGH_TICKERS + CUSTOM_TICKERS))
        logger.info(f"Loaded {len(combined)} tickers for universal data load (SNP500 + HIGH + CUSTOM)")
        return combined
