from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import Backtester
from .config import load_config
from .data import load_candles
from .optimization import run_grid_search
from .reporting import format_metrics, load_json_report, write_json_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fixed-capital crypto scalping bot framework")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtest = subparsers.add_parser("backtest", help="Run a backtest using sample or custom data")
    backtest.add_argument("--config", required=True)
    backtest.add_argument("--data", required=True)
    backtest.add_argument("--report", default="reports/backtest_report.json")

    optimize = subparsers.add_parser("optimize", help="Run parameter optimization")
    optimize.add_argument("--config", required=True)
    optimize.add_argument("--data", required=True)
    optimize.add_argument("--report", default="reports/optimization_results.json")
    optimize.add_argument("--top", type=int, default=None)

    summary = subparsers.add_parser("summary", help="Print a saved performance summary report")
    summary.add_argument("--report", required=True)

    return parser


def command_backtest(config_path: str, data_path: str, report_path: str) -> int:
    config = load_config(config_path)
    candles = load_candles(data_path)
    result = Backtester(config).run(candles)
    write_json_report(report_path, result.to_dict())
    print(format_metrics(result.metrics))
    print(f"\nSaved backtest report to {Path(report_path).resolve()}")
    return 0


def command_optimize(config_path: str, data_path: str, report_path: str, top: int | None) -> int:
    config = load_config(config_path)
    candles = load_candles(data_path)
    result = run_grid_search(config, candles, top_n=top)
    write_json_report(report_path, result)
    print("Best parameter set:")
    for key, value in result["best_parameters"].items():
        print(f"- {key}: {value}")
    print("\nBest metrics:")
    print(format_metrics(result["best_metrics"]))
    print(f"\nSaved optimization report to {Path(report_path).resolve()}")
    return 0


def command_summary(report_path: str) -> int:
    report = load_json_report(report_path)
    metrics = report.get("metrics") or report.get("best_metrics")
    if not metrics:
        raise ValueError("Report does not include a metrics payload.")
    print(format_metrics(metrics))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "backtest":
        return command_backtest(args.config, args.data, args.report)
    if args.command == "optimize":
        return command_optimize(args.config, args.data, args.report, args.top)
    if args.command == "summary":
        return command_summary(args.report)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
