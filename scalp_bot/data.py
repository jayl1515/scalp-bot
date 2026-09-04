from __future__ import annotations

import csv
from datetime import datetime, time, timezone
from pathlib import Path

from .models import Candle


def load_candles(path: str | Path) -> list[Candle]:
    candles: list[Candle] = []
    with Path(path).open("r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
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


def _parse_boundary(value: str | None, *, is_end: bool) -> datetime | None:
    if not value:
        return None
    if "T" not in value and " " not in value:
        parsed_date = datetime.fromisoformat(value).date()
        parsed = datetime.combine(parsed_date, time.max if is_end else time.min)
    else:
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def filter_candles(
    candles: list[Candle],
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[Candle]:
    start_at = _parse_boundary(start, is_end=False)
    end_at = _parse_boundary(end, is_end=True)
    filtered: list[Candle] = []
    for candle in candles:
        if start_at and candle.timestamp < start_at:
            continue
        if end_at and candle.timestamp > end_at:
            continue
        filtered.append(candle)
    return filtered


def candle_time_range(candles: list[Candle]) -> tuple[str | None, str | None]:
    if not candles:
        return None, None
    return candles[0].timestamp.isoformat(), candles[-1].timestamp.isoformat()
