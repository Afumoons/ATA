"""Run Stage 1 shadow ML predictions for configured symbols."""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import replace
from pathlib import Path

from autonomous_trading_ai.config import ml_config
from autonomous_trading_ai.ml.predict import run_shadow_prediction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Journal shadow-only ML predictions")
    parser.add_argument("--symbol", action="append", dest="symbols", help="Symbol to predict; repeatable. Defaults to ML config symbols.")
    parser.add_argument("--timeframe", default=ml_config.timeframe)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--journal", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Evaluate fail-closed paths without writing prediction records.")
    parser.add_argument(
        "--enable-shadow",
        action="store_true",
        help="Opt in to Stage 1 shadow journaling for this run. Still never permits execution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = replace(ml_config, enabled=True, stage="shadow") if args.enable_shadow else ml_config
    symbols = args.symbols or cfg.managed_symbols
    total_written = 0
    dry_run_dir = tempfile.TemporaryDirectory() if args.dry_run else None
    dry_run_journal = Path(dry_run_dir.name) / "prediction.jsonl" if dry_run_dir else None
    try:
        for symbol in symbols:
            result = run_shadow_prediction(
                symbol=symbol,
                timeframe=args.timeframe,
                config=cfg,
                base_dir=args.base_dir,
                registry_path=args.registry,
                prediction_journal_path=dry_run_journal or args.journal,
            )
            total_written += result.written
            prefix = "dry-run " if args.dry_run else ""
            print(
                f"{prefix}{symbol} {args.timeframe}: attempted={result.attempted} written={result.written} "
                f"skipped={result.skipped} reasons={result.reasons}"
            )
    finally:
        if dry_run_dir is not None:
            dry_run_dir.cleanup()
    return 0 if total_written or not cfg.enabled or args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
