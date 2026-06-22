"""Market-data adapter (architecture Section 4.1 "Market-Data Adapter
(iface)", Section 7.2 trade cycle step 3a, PRD Section 7).

Provider-agnostic interface (`MarketDataProvider`) with a yfinance-backed
primary implementation (`YFinanceProvider`). Alpha Vantage is documented
as the config-swappable fallback (architecture 2 tech-stack table /
assumption 10) but is NOT implemented in this slice — `AlphaVantageProvider`
below is a stub that raises NotImplementedError, kept only so the adapter
interface shape is visible and a future slice can fill it in without
touching call sites.

Core entrypoint: `get_daily_bars(db, ticker, lookback_days, as_of)`.
Cache-first (architecture 7.2 step 3a):
  - read market_data_cache for the needed (ticker, bar_date) range
  - on a gap, fetch the missing range from the provider and write
    immutable cache rows (architecture 3.2: unique (ticker, bar_date),
    write-once, never re-fetched)
  - on a fetch error, raise MarketDataFetchError — a typed error the
    engine catches, logs, and skips that ticker for the run (architecture
    7.2 step 3a "fetch error -> log, append to errors, SKIP ticker";
    PRD 7.3). This module never crashes the caller; it only raises a
    typed exception the caller is expected to catch.

The actual network call (`YFinanceProvider._fetch`) is isolated into its
own method specifically so tests can monkeypatch it with synthetic bars
instead of hitting the real yfinance/Yahoo endpoint (task requirement).
"""

import datetime
import decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketDataCache

logger = logging.getLogger(__name__)


class MarketDataFetchError(Exception):
    """Raised when a provider fails to return bars for a ticker.

    Caught by the engine signal layer (app/engine/runner.py), which logs
    it, records it in engine_runs.errors, and skips that ticker for the
    run rather than letting the exception propagate and fail the whole run.
    """


class Bar:
    """One immutable daily OHLCV bar. Plain value object, not an ORM row,
    so callers (indicators, signals) don't need a DB session to use it.
    """

    __slots__ = ("ticker", "bar_date", "open", "high", "low", "close", "volume")

    def __init__(
        self,
        ticker: str,
        bar_date: datetime.date,
        open: decimal.Decimal,
        high: decimal.Decimal,
        low: decimal.Decimal,
        close: decimal.Decimal,
        volume: int,
    ):
        self.ticker = ticker
        self.bar_date = bar_date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class MarketDataProvider:
    """Adapter interface. Concrete providers implement `_fetch`."""

    name = "base"

    def _fetch(
        self, ticker: str, start: datetime.date, end: datetime.date
    ) -> list[Bar]:
        """Fetch raw bars for [start, end] (inclusive) from the external
        source. Must raise MarketDataFetchError on any failure. Returns
        bars sorted oldest-first; may legitimately return fewer bars than
        requested (weekends/holidays/newly-listed tickers).
        """
        raise NotImplementedError


class YFinanceProvider(MarketDataProvider):
    """Primary provider (architecture 2 / PRD 7.1). No API key required."""

    name = "yfinance"

    def _fetch(
        self, ticker: str, start: datetime.date, end: datetime.date
    ) -> list[Bar]:
        try:
            import yfinance as yf

            # yfinance's `end` is exclusive, so widen by one day to include it.
            df = yf.Ticker(ticker).history(
                start=start.isoformat(),
                end=(end + datetime.timedelta(days=1)).isoformat(),
                interval="1d",
            )
        except Exception as exc:  # network error, bad ticker, library error, etc.
            raise MarketDataFetchError(f"yfinance fetch failed for {ticker}: {exc}") from exc

        if df is None or df.empty:
            raise MarketDataFetchError(f"yfinance returned no data for {ticker}")

        bars = []
        for index, row in df.iterrows():
            bar_date = index.date() if hasattr(index, "date") else index
            bars.append(
                Bar(
                    ticker=ticker,
                    bar_date=bar_date,
                    open=decimal.Decimal(str(row["Open"])),
                    high=decimal.Decimal(str(row["High"])),
                    low=decimal.Decimal(str(row["Low"])),
                    close=decimal.Decimal(str(row["Close"])),
                    volume=int(row["Volume"]),
                )
            )
        return bars


class AlphaVantageProvider(MarketDataProvider):
    """Fallback provider stub (architecture 2 tech-stack table / PRD 7.1,
    assumption 10). NOT implemented in this slice — config-swappable shape
    only, so a future slice can add the real HTTP call behind this same
    interface without changing any call site in the engine.
    """

    name = "alphavantage"

    def _fetch(
        self, ticker: str, start: datetime.date, end: datetime.date
    ) -> list[Bar]:
        raise NotImplementedError("Alpha Vantage fallback is not implemented in this slice")


def _upsert_cache_rows(db: Session, provider_name: str, bars: list[Bar]) -> None:
    """Write fetched bars to market_data_cache, skipping any (ticker,
    bar_date) already present (immutable cache — architecture 3.2 unique
    constraint, write-once, never re-fetched/never updated).
    """
    if not bars:
        return

    existing_dates = set(
        db.execute(
            select(MarketDataCache.bar_date).where(
                MarketDataCache.ticker == bars[0].ticker,
                MarketDataCache.bar_date.in_([b.bar_date for b in bars]),
            )
        )
        .scalars()
        .all()
    )

    for bar in bars:
        if bar.bar_date in existing_dates:
            continue
        db.add(
            MarketDataCache(
                ticker=bar.ticker,
                bar_date=bar.bar_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                provider=provider_name,
            )
        )
    db.flush()


def get_daily_bars(
    db: Session,
    ticker: str,
    lookback_days: int,
    as_of: datetime.date,
    provider: MarketDataProvider | None = None,
) -> list[Bar]:
    """Cache-first daily bars for `ticker` ending on/before `as_of`,
    covering roughly `lookback_days` calendar days back (architecture 4.1
    pseudocode `market_data.get_daily_bars(universe, lookback)`).

    Strategy: read whatever's cached for the window; if the cache fully
    covers the window through `as_of` it's used as-is (no network call).
    Otherwise the provider is asked for the full window in one call
    (architecture 7.3 "request the full range in one call per ticker") and
    the result is merged into the cache before being returned. On a fetch
    error, MarketDataFetchError propagates to the caller (engine signal
    layer), which is responsible for catching it, logging, and skipping
    this ticker (architecture 7.2 step 3a).

    `lookback_days` is calendar days, not trading days, intentionally
    generous (covers weekends/holidays) so the slice of returned bars is
    at least long enough for the longest indicator window.
    """
    provider = provider or YFinanceProvider()
    start = as_of - datetime.timedelta(days=lookback_days)

    cached = (
        db.execute(
            select(MarketDataCache)
            .where(
                MarketDataCache.ticker == ticker,
                MarketDataCache.bar_date >= start,
                MarketDataCache.bar_date <= as_of,
            )
            .order_by(MarketDataCache.bar_date)
        )
        .scalars()
        .all()
    )

    cache_covers_as_of = bool(cached) and cached[-1].bar_date >= as_of - datetime.timedelta(days=4)
    # The cache "covers" the request if its most recent row is within a
    # few days of as_of (handles weekends/holidays where as_of itself has
    # no bar) — otherwise treat it as stale/incomplete and re-fetch the
    # full window. Cache hits never re-fetch already-cached dates either
    # way (architecture 7.3); this only decides whether a fetch is needed
    # at all.
    if cache_covers_as_of:
        return [
            Bar(
                ticker=row.ticker,
                bar_date=row.bar_date,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in cached
        ]

    fetched = provider._fetch(ticker, start, as_of)
    _upsert_cache_rows(db, provider.name, fetched)

    merged = (
        db.execute(
            select(MarketDataCache)
            .where(
                MarketDataCache.ticker == ticker,
                MarketDataCache.bar_date >= start,
                MarketDataCache.bar_date <= as_of,
            )
            .order_by(MarketDataCache.bar_date)
        )
        .scalars()
        .all()
    )
    return [
        Bar(
            ticker=row.ticker,
            bar_date=row.bar_date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
        )
        for row in merged
    ]
