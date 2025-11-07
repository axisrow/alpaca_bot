"""Tests for verifying DataLoader caching matches raw yfinance payloads."""
import pickle
import logging

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest
import yfinance as yf

import data_loader

logger = logging.getLogger(__name__)


def _sample_yf_payload() -> pd.DataFrame:
    """Build a minimal MultiIndex frame similar to yfinance output.

    Real yfinance structure (with group_by='ticker'):
    - Level 0: Ticker names (AAA, BBB, ...)
    - Level 1: OHLCV fields (Close, Volume, ...)
    """

    index = pd.date_range("2024-01-01", periods=2, freq="D", name="Date")
    columns = pd.MultiIndex.from_arrays(
        [
            ["AAA", "AAA", "BBB", "BBB"],  # Level 0: Ticker
            ["Close", "Volume", "Close", "Volume"],  # Level 1: Price field
        ],
        names=["Ticker", "Price"],
    )
    data = pd.DataFrame(
        [[10.0, 100, 20.0, 200], [11.0, 110, 21.0, 210]],
        index=index,
        columns=columns,
    )
    return data


def test_cache_persists_raw_yfinance_payload(tmp_path, monkeypatch):
    """Ensure cache stores exactly what yfinance returns and is reused."""

    cache_dir = tmp_path / "cache"
    cache_file = cache_dir / "cache.pkl"
    monkeypatch.setattr(data_loader, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(data_loader, "CACHE_FILE", cache_file)

    source_frame = _sample_yf_payload()

    download_calls: list[pd.DataFrame] = []

    def fake_download(tickers, **kwargs):  # noqa: ARG001
        payload = source_frame.copy()
        download_calls.append(payload)
        return payload

    monkeypatch.setattr(data_loader.yf, "download", fake_download)

    loaded = data_loader.DataLoader.load_market_data(period="1y")
    assert_frame_equal(loaded, source_frame)
    assert len(download_calls) == 1

    with cache_file.open("rb") as cache_fp:
        cached_frame = pickle.load(cache_fp)

    assert_frame_equal(cached_frame, source_frame)

    def fail_download(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("load_market_data should use cache when valid")

    monkeypatch.setattr(data_loader.yf, "download", fail_download)
    cached_loaded = data_loader.DataLoader.load_market_data(period="1y")
    assert_frame_equal(cached_loaded, source_frame)


@pytest.mark.integration
def test_real_yfinance_caching(tmp_path, monkeypatch):
    """Integration test: verify caching works with real yfinance data.

    This test:
    1. Downloads real data from yfinance (3 tickers, 5 days)
    2. Saves it via DataLoader._save_to_cache()
    3. Loads it via DataLoader._load_from_cache()
    4. Verifies the data is identical after roundtrip
    5. Checks that momentum calculations work correctly

    This test requires internet and takes ~2-3 seconds.
    Run with: pytest -m integration tests/test_data_loader_cache.py::test_real_yfinance_caching
    """
    cache_dir = tmp_path / "cache_integration"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "cache.pkl"
    monkeypatch.setattr(data_loader, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(data_loader, "CACHE_FILE", cache_file)

    logger.info("Step 1: Download real data from yfinance...")
    tickers = ["AAPL", "GOOGL", "MSFT"]
    original_data = yf.download(
        tickers,
        period="5d",
        group_by="ticker",
        auto_adjust=True,
        progress=False
    )

    logger.info(f"Downloaded {original_data.shape[0]} rows × {original_data.shape[1]} columns")

    # Verify structure
    assert isinstance(original_data, pd.DataFrame)
    assert isinstance(original_data.index, pd.DatetimeIndex)
    assert isinstance(original_data.columns, pd.MultiIndex)
    assert original_data.columns.nlevels == 2
    assert "Close" in original_data.columns.get_level_values(1)

    logger.info("Step 2: Save via DataLoader._save_to_cache()...")
    data_loader.DataLoader._save_to_cache(original_data)
    assert cache_file.exists(), "Cache file was not created"

    logger.info(f"Saved {cache_file.stat().st_size / 1024:.1f} KB to {cache_file}")

    logger.info("Step 3: Load via DataLoader._load_from_cache()...")
    loaded_data = data_loader.DataLoader._load_from_cache()

    logger.info(f"Loaded {loaded_data.shape[0]} rows × {loaded_data.shape[1]} columns")

    # Verify structure matches
    assert loaded_data.shape == original_data.shape, \
        f"Shape mismatch: {loaded_data.shape} != {original_data.shape}"

    assert loaded_data.columns.equals(original_data.columns), \
        "Column structure mismatch"

    assert loaded_data.index.equals(original_data.index), \
        "Index (dates) mismatch"

    logger.info("Step 4: Verify data values match (within floating point tolerance)...")
    assert_frame_equal(loaded_data, original_data, check_exact=False, rtol=1e-10)
    logger.info("✓ Data values match exactly")

    logger.info("Step 5: Verify momentum calculation works...")
    close_original = original_data.xs("Close", level=1, axis=1)
    close_loaded = loaded_data.xs("Close", level=1, axis=1)

    # Calculate 5-day returns
    returns_original = (close_original.iloc[-1] / close_original.iloc[0] - 1) * 100
    returns_loaded = (close_loaded.iloc[-1] / close_loaded.iloc[0] - 1) * 100

    # Verify returns are available for all tickers
    assert len(returns_original) == len(tickers), f"Missing returns for some tickers"
    assert not returns_original.isna().any(), "NaN values in original returns"
    assert not returns_loaded.isna().any(), "NaN values in loaded returns"

    # Verify returns match (should be identical)
    assert_frame_equal(
        returns_original.to_frame().T,
        returns_loaded.to_frame().T,
        check_exact=False,
        rtol=1e-15
    )

    logger.info(f"Returns (original): {returns_original.to_dict()}")
    logger.info(f"Returns (loaded):   {returns_loaded.to_dict()}")
    logger.info("✓ Momentum calculation works correctly after caching")

    logger.info("✓ Integration test passed: caching is 1:1 with yfinance data")
