"""Market data loading and caching helpers."""
import logging
import os
import pickle
import time
from datetime import datetime, timedelta
from typing import List

import pandas as pd
import yfinance as yf

from config import (
    ENVIRONMENT,
    SNP500_TICKERS,
    HIGH_TICKERS,
    CUSTOM_TICKERS,
    CACHE_DIR,
    CACHE_FILE,
    CACHE_VALIDITY_HOURS,
    MARKET_DATA_PERIOD,
    MARKET_DATA_MAX_RETRIES,
    MARKET_DATA_RETRY_DELAY_SECONDS,
    MARKET_DATA_ENABLE_RETRY,
)

logger = logging.getLogger(__name__)

FAILED_TICKERS: List[str] = []


def load_market_data() -> pd.DataFrame:
    """Load market data from cache or yfinance using config-defined params."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _is_cache_valid():
        logger.info("Loading data from cache")
        return _load_from_cache()

    logger.info("Loading data from yfinance")
    tickers = list(set(SNP500_TICKERS + HIGH_TICKERS + CUSTOM_TICKERS))
    data = _download_with_retry(tickers)

    if data is None or data.empty:
        logger.error("Failed to download market data")
        raise ValueError("No data downloaded from yfinance")

    if 'Close' not in data.columns.get_level_values(0):
        logger.error("'Close' column not found in downloaded data")
        raise ValueError("'Close' column not found in data")

    _update_failed_tickers(tickers, data)
    _save_to_cache(data)
    logger.info("Data cached successfully")
    return data


def clear_cache() -> None:
    """Remove the cached market data file."""
    cache_path = CACHE_FILE
    if cache_path.exists():
        cache_path.unlink()
        logger.info("Cache cleared")
    else:
        logger.info("Cache file does not exist")


def get_snp500_tickers() -> List[str]:
    """Return combined ticker universe for all strategies."""
    combined = list(set(SNP500_TICKERS + HIGH_TICKERS + CUSTOM_TICKERS))
    logger.info("Loaded %d tickers for universal data load (SNP500 + HIGH + CUSTOM)", len(combined))
    return combined


def _download_with_retry(tickers: List[str]) -> pd.DataFrame:
    """Download market data with retry support, retrying missing tickers."""
    remaining = list(dict.fromkeys(tickers))
    combined_data: pd.DataFrame | None = None
    last_exception: Exception | None = None

    max_attempts = MARKET_DATA_MAX_RETRIES if MARKET_DATA_ENABLE_RETRY else 1
    yf_logger = logging.getLogger("yfinance")
    original_disabled = getattr(yf_logger, 'disabled', False)
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                yf_logger.disabled = attempt < max_attempts
                logger.info(
                    "Downloading market data (attempt %d/%d, tickers=%d)",
                    attempt,
                    max_attempts,
                    len(remaining),
                )
                data = yf.download(
                    tickers=remaining,
                    period=MARKET_DATA_PERIOD,
                    threads=True,
                    auto_adjust=True,
                    progress=ENVIRONMENT == "local",
                )

                if data is None or data.empty:
                    raise ValueError("No data downloaded from yfinance")

                combined_data = data if combined_data is None else pd.concat([combined_data, data], axis=1)
                missing = _find_missing_tickers(remaining, data)

                if missing and attempt < max_attempts:
                    preview = missing[:10]
                    logger.warning(
                        "Attempt %d/%d: %d tickers timed out (%s). Retrying remaining in %ds...",
                        attempt,
                        max_attempts,
                        len(missing),
                        preview,
                        MARKET_DATA_RETRY_DELAY_SECONDS,
                    )
                    remaining = missing
                    time.sleep(MARKET_DATA_RETRY_DELAY_SECONDS)
                    continue

                if missing:
                    logger.error(
                        "Failed to download %d tickers after %d attempts: %s",
                        len(missing),
                        max_attempts,
                        missing[:20] if len(missing) > 20 else missing,
                    )

                return combined_data

            except Exception as exc:  # pylint: disable=broad-exception-caught
                last_exception = exc
                if attempt < max_attempts:
                    logger.warning(
                        "Attempt %d failed: %s. Retrying in %ds...",
                        attempt,
                        exc,
                        MARKET_DATA_RETRY_DELAY_SECONDS,
                    )
                    time.sleep(MARKET_DATA_RETRY_DELAY_SECONDS)
                else:
                    logger.error(
                        "Failed to download market data after %d attempts: %s",
                        max_attempts,
                        exc,
                        exc_info=True,
                    )
    finally:
        yf_logger.disabled = original_disabled

    raise last_exception if last_exception else RuntimeError("Market data download failed without exception")


def _find_missing_tickers(expected: List[str], data: pd.DataFrame) -> List[str]:
    """Return a list of tickers missing from the downloaded dataset."""
    downloaded: set[str] = set()

    if isinstance(data.columns, pd.MultiIndex):
        level0 = data.columns.get_level_values(0)
        if 'Close' in level0:
            close_data = data['Close']
            # Only include tickers that have at least one valid (non-NaN) value
            downloaded = set(close_data.columns[close_data.notna().any()])
        else:
            downloaded = set(data.columns.get_level_values(-1))
    elif len(expected) == 1:
        downloaded = {expected[0]}

    return [symbol for symbol in expected if symbol not in downloaded]


def _update_failed_tickers(expected: List[str], data: pd.DataFrame) -> None:
    """Track tickers that failed to download."""
    failed = _find_missing_tickers(expected, data)
    if not failed:
        FAILED_TICKERS.clear()
        return

    FAILED_TICKERS.clear()
    FAILED_TICKERS.extend(failed)
    logger.warning(
        "Failed to download %d/%d tickers: %s",
        len(failed),
        len(expected),
        failed[:20] if len(failed) > 20 else failed,
    )


def _is_cache_valid() -> bool:
    """Return True if cache exists and is younger than configured validity window."""
    cache_path = CACHE_FILE
    if not cache_path.exists():
        return False

    file_mtime = os.path.getmtime(cache_path)
    file_age = datetime.now() - datetime.fromtimestamp(file_mtime)
    is_valid = file_age < timedelta(hours=CACHE_VALIDITY_HOURS)

    if is_valid:
        logger.debug("Cache is valid (age: %s)", file_age)
    else:
        logger.debug("Cache is expired (age: %s)", file_age)
    return is_valid


def _load_from_cache() -> pd.DataFrame:
    """Load cached market data."""
    cache_path = CACHE_FILE
    with open(cache_path, "rb") as cache_file:
        data = pickle.load(cache_file)
    logger.info("Loaded %d rows from cache", len(data))
    return data


def _save_to_cache(data: pd.DataFrame) -> None:
    """Persist market data to cache."""
    cache_path = CACHE_FILE
    with open(cache_path, "wb") as cache_file:
        pickle.dump(data, cache_file)
    logger.debug("Data cached to %s", cache_path)


__all__ = [
    "FAILED_TICKERS",
    "load_market_data",
    "clear_cache",
    "get_snp500_tickers",
]
