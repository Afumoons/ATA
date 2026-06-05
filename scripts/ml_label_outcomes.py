"""Resolve pending Stage 1 shadow ML outcomes."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from autonomous_trading_ai.config import ml_config
from autonomous_trading_ai.ml.dataset import load_feature_frame
from autonomous_trading_ai.ml.outcome import label_pending_predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Label pending shadow ML prediction outcomes")
    parser.add_argument("--prediction-journal", type=Path, required=True)
    parser.add_argument("--outcome-journal", type=Path, default=None)
    parser.add_argument("--symbol", action="append", dest="symbols", help="Symbol to load; repeatable. Defaults to ML config symbols.")
    parser.add_argument("--timeframe", default=ml_config.timeframe)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Resolve outcomes into a temporary journal without writing the configured outcome file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    frames = {}
    for symbol in args.symbols or ml_config.managed_symbols:
        try:
            frames[(symbol, args.timeframe)] = load_feature_frame(symbol, args.timeframe, base_dir=args.base_dir)
        except FileNotFoundError as exc:
            print(f"skip {symbol} {args.timeframe}: {exc}")
    dry_run_dir = tempfile.TemporaryDirectory() if args.dry_run else None
    try:
        outcome_path = Path(dry_run_dir.name) / "outcome.jsonl" if dry_run_dir else args.outcome_journal
        written = label_pending_predictions(
            prediction_journal_path=args.prediction_journal,
            outcome_journal_path=outcome_path,
            feature_frames=frames,
            horizon_bars=ml_config.primary_horizon_bars,
            neutral_threshold_atr=ml_config.neutral_return_threshold_atr,
        )
        prefix = "dry-run " if args.dry_run else ""
        print(f"{prefix}outcomes_written={written}")
    finally:
        if dry_run_dir is not None:
            dry_run_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
