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
from autonomous_trading_ai.ml.quality import assess_model_action
from autonomous_trading_ai.ml.registry import load_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit shadow ML journal quality")
    parser.add_argument(
        "--prediction-journal",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "ml" / "prediction_journal.jsonl",
    )
    parser.add_argument(
        "--outcome-journal",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "ml" / "outcome_journal.jsonl",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Filter to specific symbols; repeatable. Defaults to ML config managed symbols.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON file to write the report to.")
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "ml" / "registry.json",
        help="Optional ML registry to source validation metrics from.",
    )
    return parser.parse_args()


def _filter_journal(path: Path, symbols: set[str]) -> list[dict[str, object]]:
    records = read_jsonl(path)
    if not symbols:
        return records
    return [record for record in records if str(record.get("symbol")) in symbols]


def _attach_recommendations(report: dict[str, object], registry_path: Path | None = None) -> dict[str, object]:
    registry = load_registry(registry_path)
    model_metadata = registry.model_metadata
    recommendations: dict[str, object] = {}
    by_model = report.get("by_model", {}) if isinstance(report, dict) else {}
    for model_id, model_report in by_model.items():
        metadata = model_metadata.get(model_id)
        if metadata is None:
            continue
        recommendation = assess_model_action(metadata.metrics, model_report, config=ml_config)
        recommendation["model_id"] = model_id
        recommendation["symbol"] = metadata.symbol
        recommendation["timeframe"] = metadata.timeframe
        recommendation["validation_report_path"] = metadata.validation_report_path
        recommendations[f"{metadata.symbol}:{metadata.timeframe}"] = recommendation
    report["recommendations"] = recommendations
    report["phase_2_summary"] = {
        "keep_shadow_only": sum(1 for item in recommendations.values() if item["next_action"] == "keep_shadow_only"),
        "retrain": sum(1 for item in recommendations.values() if item["next_action"] == "retrain"),
        "revise_labels_features": sum(1 for item in recommendations.values() if item["next_action"] == "revise_labels_features"),
        "promotion_ready": sum(1 for item in recommendations.values() if item["promotion_ready"]),
    }
    return report


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
        report = _attach_recommendations(report, args.registry)
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
