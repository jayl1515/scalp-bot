"""Exchange-backed historical market data with a local CSV cache."""
from __future__ import annotations

import csv
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

from .data import filter_candles
from .models import Candle


DEFAULT_EXCHANGE = "binance"
DEFAULT_CACHE_DIR = Path("data") / "market_cache"


def _parse_boundary(value: str | None, *, is_end: bool) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if "T" not in value and " " not in value:
        parsed = parsed.replace(hour=23 if is_end else 0, minute=59 if is_end else 0, second=59 if is_end else 0, microsecond=999999 if is_end else 0)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _safe_part(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _cache_path(cache_dir: Path, exchange: str, symbol: str, timeframe: str) -> Path:
    return cache_dir / f"{_safe_part(exchange)}_{_safe_part(symbol)}_{_safe_part(timeframe)}.csv"


def cache_path(
    *,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> Path:
    return _cache_path(Path(cache_dir), exchange_id, symbol, timeframe)


def cache_summary(
    *,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    path = cache_path(
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        cache_dir=cache_dir,
    )
    candles = _load_cache(path)
    start_at, end_at = (None, None)
    if candles:
        start_at = candles[0].timestamp.isoformat()
        end_at = candles[-1].timestamp.isoformat()
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "total_candles": len(candles),
        "start_at": start_at,
        "end_at": end_at,
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat() if path.exists() else None,
    }


def _load_cache(path: Path) -> list[Candle]:
    if not path.exists():
        return []
    candles: list[Candle] = []
    with path.open("r", newline="") as handle:
        for row in csv.DictReader(handle):
            candles.append(
                Candle(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return candles


def _save_cache(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for candle in candles:
            writer.writerow({
                "timestamp": candle.timestamp.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            })


def _build_exchange(exchange_id: str) -> Any:
    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("Live market data requires ccxt. Install dependencies with: pip install -r requirements.txt") from exc
    try:
        exchange_class = getattr(ccxt, exchange_id)
    except AttributeError as exc:
        raise ValueError(f"Unsupported exchange: {exchange_id}") from exc
    return exchange_class({"enableRateLimit": True})


def _timeframe_milliseconds(exchange: Any, timeframe: str) -> int:
    milliseconds = exchange.parse_timeframe(timeframe) * 1000
    if milliseconds <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return milliseconds


def fetch_historical_candles(
    *,
    exchange_id: str = DEFAULT_EXCHANGE,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    exchange: Any | None = None,
) -> list[Candle]:
    """Fetch and cache OHLCV candles for an exchange market.

    The exchange object is injectable for deterministic tests. Public OHLCV
    endpoints do not require API credentials, but symbols must exist on the
    selected exchange and market type.
    """
    start_at = _parse_boundary(start, is_end=False)
    end_at = _parse_boundary(end, is_end=True)
    if start_at is None or end_at is None or start_at > end_at:
        raise ValueError("A valid start and end date are required.")

    cache_path = _cache_path(Path(cache_dir), exchange_id, symbol, timeframe)
    cached = _load_cache(cache_path)
    matching = filter_candles(cached, start=start, end=end)
    if matching and matching[0].timestamp <= start_at and matching[-1].timestamp >= end_at:
        return matching

    client = exchange or _build_exchange(exchange_id)
    markets = client.load_markets()
    if symbol not in markets:
        raise ValueError(f"Symbol '{symbol}' is not available on {exchange_id}.")
    if timeframe not in (client.timeframes or {}):
        raise ValueError(f"Timeframe '{timeframe}' is not available on {exchange_id}.")

    timeframe_ms = _timeframe_milliseconds(client, timeframe)
    since_ms = int(start_at.timestamp() * 1000)
    end_ms = int(end_at.timestamp() * 1000)
    fetched: list[Candle] = []
    while since_ms <= end_ms:
        batch = client.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=1000)
        if not batch:
            break
        for row in batch:
            if len(row) < 6:
                continue
            timestamp = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).replace(tzinfo=None)
            if start_at <= timestamp <= end_at:
                fetched.append(Candle(timestamp, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])))
        newest_ms = int(batch[-1][0])
        next_since = newest_ms + timeframe_ms
        if next_since <= since_ms:
            break
        since_ms = next_since

    combined = {candle.timestamp: candle for candle in cached}
    combined.update({candle.timestamp: candle for candle in fetched})
    all_candles = [combined[key] for key in sorted(combined)]
    _save_cache(cache_path, all_candles)
    return filter_candles(all_candles, start=start, end=end)
