from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BacktestMetrics


def write_json_report(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))


def load_json_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def format_metrics(metrics: BacktestMetrics | dict[str, Any]) -> str:
    data = metrics.to_dict() if hasattr(metrics, "to_dict") else metrics
    profit_factor = data["profit_factor"]
    profit_factor_text = "inf" if profit_factor == float("inf") else f"{profit_factor:.2f}"
    lines = [
        f"Win rate: {data['win_rate']:.2f}%",
        f"Net PnL: ${data['net_pnl']:.2f}",
        f"Profit factor: {profit_factor_text}",
        f"Max drawdown: ${data['max_drawdown']:.2f}",
        f"Total trades: {data['total_trades']}",
        f"Average win: ${data['average_win']:.2f}",
        f"Average loss: ${data['average_loss']:.2f}",
        f"Trading balance: ${data['ending_trading_balance']:.2f}",
        f"Profit wallet: ${data['profit_wallet_balance']:.2f}",
        f"Total equity: ${data['total_equity']:.2f}",
        f"Stopped days: {data['stopped_days']}",
        f"Risk-adjusted score: {data['risk_adjusted_score']:.4f}",
    ]
    return "\n".join(lines)
