"""Train Stage 1 shadow ML models for configured symbols."""

from __future__ import annotations

import argparse
from pathlib import Path

from autonomous_trading_ai.config import ml_config
from autonomous_trading_ai.ml.dataset import build_ml_dataset
from autonomous_trading_ai.ml.train import train_shadow_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train shadow-only ML signal models")
    parser.add_argument("--symbol", action="append", dest="symbols", help="Symbol to train; repeatable. Defaults to ML config symbols.")
    parser.add_argument("--timeframe", default=ml_config.timeframe)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--artifact-dir", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Build datasets and print split sizes without writing artifacts.")
    parser.add_argument(
        "--model-kind",
        choices=("logistic_regression", "hist_gradient_boosting"),
        default="logistic_regression",
        help="Sklearn baseline model type for Stage 1 shadow training.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = args.symbols or ml_config.managed_symbols
    for symbol in symbols:
        if args.dry_run:
            dataset = build_ml_dataset(symbol, args.timeframe, ml_config, base_dir=args.base_dir)
            print(
                f"dry-run {symbol} {args.timeframe}: features={len(dataset.feature_columns)} "
                f"train={len(dataset.train)} validation={len(dataset.validation)} test={len(dataset.test)}"
            )
            continue
        metadata = train_shadow_model(
            symbol=symbol,
            timeframe=args.timeframe,
            config=ml_config,
            base_dir=args.base_dir,
            artifact_dir=args.artifact_dir,
            registry_path=args.registry,
            model_kind=args.model_kind,
        )
        print(f"trained shadow model {metadata.model_id} for {symbol} {args.timeframe}")
        print(f"  artifact: {metadata.artifact_path}")
        print(f"  metrics: {metadata.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
