"""Server-side validation for control panel settings updates."""
from __future__ import annotations

from typing import Any


_FLOAT_FIELDS: dict[str, tuple[float, float]] = {
    "base_capital": (1.0, 1_000_000.0),
    "fee_rate": (0.0, 0.1),
    "slippage_bps": (0.0, 100.0),
    "risk.max_daily_loss_pct": (0.001, 1.0),
    "risk.risk_per_trade_pct": (0.001, 1.0),
    "strategy.risk_per_trade_pct": (0.001, 1.0),
    "strategy.max_position_pct": (0.01, 1.0),
    "strategy.stop_atr_multiple": (0.1, 10.0),
    "strategy.reward_to_risk": (0.1, 20.0),
    "strategy.min_atr_pct": (0.0001, 0.1),
    "strategy.max_atr_pct": (0.001, 0.5),
    "strategy.volume_multiplier": (0.5, 10.0),
    "strategy.min_trade_notional": (0.01, 10_000.0),
}

_INT_FIELDS: dict[str, tuple[int, int]] = {
    "risk.max_consecutive_losses": (1, 100),
    "risk.cooldown_bars": (0, 1000),
    "strategy.ema_fast_period": (2, 500),
    "strategy.ema_slow_period": (3, 500),
    "strategy.atr_period": (2, 500),
    "strategy.volume_lookback": (2, 500),
    "strategy.max_hold_bars": (1, 10_000),
}

_ALLOWED_KEYS = set(_FLOAT_FIELDS) | set(_INT_FIELDS)


def _dotget(data: dict[str, Any], dotkey: str) -> Any | None:
    """Traverse nested dict with a dot-separated key."""
    parts = dotkey.split(".", 1)
    if len(parts) == 1:
        return data.get(parts[0])
    sub = data.get(parts[0])
    if not isinstance(sub, dict):
        return None
    return _dotget(sub, parts[1])


def validate_settings(data: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty = OK)."""
    errors: list[str] = []

    # Flatten the submitted payload for checking
    flat: dict[str, Any] = {}
    for top_key, top_val in data.items():
        if isinstance(top_val, dict):
            for sub_key, sub_val in top_val.items():
                flat[f"{top_key}.{sub_key}"] = sub_val
        else:
            flat[top_key] = top_val

    for key, value in flat.items():
        if key not in _ALLOWED_KEYS:
            errors.append(f"Unknown setting: '{key}'")
            continue

        if key in _FLOAT_FIELDS:
            lo, hi = _FLOAT_FIELDS[key]
            try:
                v = float(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a number")
                continue
            if not (lo <= v <= hi):
                errors.append(f"'{key}' must be between {lo} and {hi} (got {v})")

        elif key in _INT_FIELDS:
            lo, hi = _INT_FIELDS[key]
            try:
                v = int(value)
                if float(value) != v:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be an integer")
                continue
            if not (lo <= v <= hi):
                errors.append(f"'{key}' must be between {lo} and {hi} (got {v})")

    return errors
