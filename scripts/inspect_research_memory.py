from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from autonomous_trading_ai.vector_memory.research_memory import ResearchMemory
from autonomous_trading_ai.logging_utils import get_logger

logger = get_logger(__name__)


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {k: float("nan") for k in ["min", "p25", "median", "p75", "max", "mean"]}

    vals = sorted(values)
    n = len(vals)

    def q(p: float) -> float:
        if n == 1:
            return vals[0]
        idx = int(p * (n - 1))
        return vals[idx]

    return {
        "min": vals[0],
        "p25": q(0.25),
        "median": q(0.5),
        "p75": q(0.75),
        "max": vals[-1],
        "mean": statistics.fmean(vals),
    }


def _collect_stat(metadatas: list[dict], key: str) -> dict[tuple[str, str], list[float]]:
    by_symbol_tf: dict[tuple[str, str], list[float]] = defaultdict(list)
    for m in metadatas:
        v = m.get(key)
        if v is None:
            continue
        try:
            x = float(v)
        except Exception:
            continue
        sym = m.get("symbol", "?")
        tf = m.get("timeframe", "?")
        by_symbol_tf[(sym, tf)].append(x)
    return by_symbol_tf


def main() -> None:
    mem = ResearchMemory()
    res = mem.collection.get()

    ids = res.get("ids", []) or []
    metadatas = res.get("metadatas", []) or []

    total_docs = len(ids)
    logger.info("Inspecting ResearchMemory: %d docs", total_docs)

    # Collect per-symbol/timeframe stats
    sharpe = _collect_stat(metadatas, "stat_sharpe_ratio")
    pf = _collect_stat(metadatas, "stat_profit_factor")
    ret = _collect_stat(metadatas, "stat_return_pct")

    lines: list[str] = []
    lines.append("# ResearchMemory Summary")
    lines.append("")
    lines.append(f"Total documents: **{total_docs}**")
    lines.append("")

    def fmt_quantiles(name: str, data: dict[tuple[str, str], list[float]]):
        lines.append(f"## {name}")
        if not data:
            lines.append("(no data)")
            lines.append("")
            return
        for (sym, tf), vals in sorted(data.items()):
            q = _quantiles(vals)
            lines.append(
                f"- {sym} {tf} (n={len(vals)}): "
                f"min={q['min']:.3f}, p25={q['p25']:.3f}, median={q['median']:.3f}, "
                f"p75={q['p75']:.3f}, max={q['max']:.3f}, mean={q['mean']:.3f}"
            )
        lines.append("")

    fmt_quantiles("Sharpe ratio (stat_sharpe_ratio)", sharpe)
    fmt_quantiles("Profit factor (stat_profit_factor)", pf)
    fmt_quantiles("Return % (stat_return_pct)", ret)

    out_path = Path(__file__).resolve().parents[1] / "vector_memory" / "MEMORY_SUMMARY.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote ResearchMemory summary to %s", out_path)

    # Also print a short console summary for quick checks
    print("TOTAL_DOCS", total_docs)
    for (sym, tf), vals in sorted(ret.items()):
        q = _quantiles(vals)
        print(
            f"RET {sym} {tf}: n={len(vals)} "
            f"median={q['median']:.2f}% p25={q['p25']:.2f}% p75={q['p75']:.2f}%"
        )


if __name__ == "__main__":
    main()
