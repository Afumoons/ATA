"""Generate a Stage 1 shadow ML quality audit report.

The report is intended for human review during the shadow-only audit phase. It
can filter the journals to a managed symbol subset before aggregation so the
operator can focus on XAU/BTC without dragging XAG into the report.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from autonomous_trading_ai.config import ml_config
from autonomous_trading_ai.ml.evaluate import build_shadow_evaluation_report
from autonomous_trading_ai.ml.journal import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit shadow ML journal quality")
    parser.add_argument("--prediction-journal", type=Path, default=Path(__file__).resolve().parent.parent / "ml" / "prediction_journal.jsonl")
    parser.add_argument("--outcome-journal", type=Path, default=Path(__file__).resolve().parent.parent / "ml" / "outcome_journal.jsonl")
    parser.add_argument("--symbol", action="append", dest="symbols", help="Filter to specific symbols; repeatable. Defaults to ML config managed symbols.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON file to write the report to.")
    return parser.parse_args()


def _filter_journal(path: Path, symbols: set[str]) -> list[dict[str, object]]:
    records = read_jsonl(path)
    if not symbols:
        return records
    return [record for record in records if str(record.get("symbol")) in symbols]


def main() -> int:
    args = parse_args()
    symbols = set(args.symbols or ml_config.managed_symbols)
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        filtered_prediction = temp_dir / "prediction_journal.jsonl"
        filtered_outcome = temp_dir / "outcome_journal.jsonl"
        filtered_prediction.write_text(
            "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in _filter_journal(args.prediction_journal, symbols))
            + ("\n" if symbols else ""),
            encoding="utf-8",
        )
        filtered_outcome.write_text(
            "\n".join(json.dumps(record, sort_keys=True, separators=(",", ":")) for record in _filter_journal(args.outcome_journal, symbols))
            + ("\n" if symbols else ""),
            encoding="utf-8",
        )
        report = build_shadow_evaluation_report(filtered_prediction, filtered_outcome)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
