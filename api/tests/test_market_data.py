"""Tests for app/market_data.py: cache-first reads, cache writes on miss,
and typed fetch-error handling. Network calls are monkeypatched via
MarketDataProvider._fetch so no real yfinance/network call happens.
"""

import datetime
import decimal

import pytest
from sqlalchemy import select

from app.market_data import Bar, MarketDataFetchError, MarketDataProvider, get_daily_bars
from app.models import MarketDataCache

AS_OF = datetime.date(2024, 3, 15)


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, bars_by_call=None, fail=False):
        self.bars_by_call = bars_by_call or []
        self.fail = fail
        self.call_count = 0

    def _fetch(self, ticker, start, end):
        self.call_count += 1
        if self.fail:
            raise MarketDataFetchError("synthetic failure")
        return self.bars_by_call


def _synthetic_bars(ticker, start_date, n):
    bars = []
    d = start_date
    for i in range(n):
        price = decimal.Decimal("100") + i
        bars.append(
            Bar(
                ticker=ticker,
                bar_date=d,
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1_000_000,
            )
        )
        d = d + datetime.timedelta(days=1)
    return bars


def test_cache_miss_fetches_and_writes_cache(db_session):
    bars = _synthetic_bars("AAPL", AS_OF - datetime.timedelta(days=4), 5)
    provider = FakeProvider(bars_by_call=bars)

    result = get_daily_bars(db_session, "AAPL", lookback_days=10, as_of=AS_OF, provider=provider)

    assert provider.call_count == 1
    assert len(result) == 5
    cached_rows = db_session.execute(
        select(MarketDataCache).where(MarketDataCache.ticker == "AAPL")
    ).scalars().all()
    assert len(cached_rows) == 5
    assert cached_rows[0].provider == "fake"


def test_cache_hit_avoids_refetch(db_session):
    bars = _synthetic_bars("MSFT", AS_OF - datetime.timedelta(days=4), 5)
    provider = FakeProvider(bars_by_call=bars)

    get_daily_bars(db_session, "MSFT", lookback_days=10, as_of=AS_OF, provider=provider)
    assert provider.call_count == 1

    # Second call within the same cached window should not hit the
    # provider again (architecture 7.3 "never re-fetch a cached date").
    result = get_daily_bars(db_session, "MSFT", lookback_days=10, as_of=AS_OF, provider=provider)
    assert provider.call_count == 1
    assert len(result) == 5


def test_fetch_error_is_typed_and_does_not_write_cache(db_session):
    provider = FakeProvider(fail=True)

    with pytest.raises(MarketDataFetchError):
        get_daily_bars(db_session, "BADTICKER", lookback_days=10, as_of=AS_OF, provider=provider)

    cached_rows = db_session.execute(
        select(MarketDataCache).where(MarketDataCache.ticker == "BADTICKER")
    ).scalars().all()
    assert cached_rows == []


def test_cache_does_not_duplicate_rows_on_overlapping_fetch(db_session):
    bars = _synthetic_bars("NVDA", AS_OF - datetime.timedelta(days=4), 5)
    provider = FakeProvider(bars_by_call=bars)
    get_daily_bars(db_session, "NVDA", lookback_days=10, as_of=AS_OF, provider=provider)

    # Force a second fetch by asking for a far-future as_of so the
    # existing cache no longer "covers" the window, but the provider
    # returns overlapping bars again.
    later = AS_OF + datetime.timedelta(days=20)
    provider2 = FakeProvider(bars_by_call=bars)
    get_daily_bars(db_session, "NVDA", lookback_days=30, as_of=later, provider=provider2)

    cached_rows = db_session.execute(
        select(MarketDataCache).where(MarketDataCache.ticker == "NVDA")
    ).scalars().all()
    # Still only 5 rows — duplicates skipped, not inserted twice.
    assert len(cached_rows) == 5
