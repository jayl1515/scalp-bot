from __future__ import annotations

import itertools
from dataclasses import asdict, replace
from typing import Any

from .backtest import Backtester
from .config import BotConfig
from .models import BacktestMetrics


def run_grid_search(config: BotConfig, candles: list, top_n: int | None = None) -> dict[str, Any]:
    grid = config.optimization.grid
    keys = list(grid.keys())
    combinations = itertools.product(*(grid[key] for key in keys))
    results: list[dict[str, Any]] = []
    for combination in combinations:
        strategy_config = config.strategy
        for key, value in zip(keys, combination):
            strategy_config = replace(strategy_config, **{key: value})
        candidate_config = replace(config, strategy=strategy_config)
        metrics = Backtester(candidate_config).run(candles).metrics
        results.append(
            {
                "parameters": {key: value for key, value in zip(keys, combination)},
                "metrics": metrics.to_dict(),
                "score": metrics.risk_adjusted_score,
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    limit = top_n or config.optimization.top_n
    return {
        "best_parameters": results[0]["parameters"] if results else {},
        "best_metrics": results[0]["metrics"] if results else {},
        "top_results": results[:limit],
        "evaluated_combinations": len(results),
    }
