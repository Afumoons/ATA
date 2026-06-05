"""Render aggregate Stage 1 shadow ML evaluation reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_trading_ai.ml.evaluate import build_shadow_evaluation_report
from autonomous_trading_ai.ml.journal import DEFAULT_PREDICTION_JOURNAL
from autonomous_trading_ai.ml.outcome import DEFAULT_OUTCOME_JOURNAL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate shadow ML prediction/outcome journals")
    parser.add_argument("--prediction-journal", type=Path, default=DEFAULT_PREDICTION_JOURNAL)
    parser.add_argument("--outcome-journal", type=Path, default=DEFAULT_OUTCOME_JOURNAL)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON file to write the report to.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow_evaluation_report(args.prediction_journal, args.outcome_journal)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
