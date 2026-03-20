from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
POOL_PATH = BASE_DIR / "strategies" / "pool_state.json"
GENERATED_DIR = BASE_DIR / "strategies" / "generated"

# Pruning criteria:
# - Focus on XAUUSDm M15 for now.
# - Drop obviously bad / useless strategies to reduce noise.
#
# A strategy is pruned if:
#   1) symbol == "XAUUSDm" and timeframe == "M15", AND
#   2) ANY of the following groups:
#      a) Disabled / weak candidates:
#         - status in {"disabled", "candidate"} AND accepted == False
#         - AND (
#             return_pct < -3.0 OR
#             profit_factor < 1.0 OR
#             wf_overall_sharpe < 0.0 OR
#             num_trades < 10
#           )
#      b) Dummy strategies:
#         - num_trades == 0 and return_pct == 0 and accepted == False
#
# Active / exploratory strategies that are accepted and have meaningful
# trade counts are kept.


def load_pool() -> dict:
    with POOL_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_pool(pool: dict) -> None:
    tmp_path = POOL_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, sort_keys=True)
    tmp_path.replace(POOL_PATH)


def prune_pool() -> None:
    pool = load_pool()

    kept = {}
    pruned = {}

    for name, rec in pool.items():
        stats = rec.get("stats", {}) or {}
        symbol = rec.get("symbol")
        timeframe = rec.get("timeframe")
        status = rec.get("status")

        # Only prune XAUUSDm M15 for now
        if symbol != "XAUUSDm" or timeframe != "M15":
            kept[name] = rec
            continue

        accepted = bool(stats.get("accepted", False))
        return_pct = float(stats.get("return_pct", 0.0) or 0.0)
        pf = float(stats.get("profit_factor", 0.0) or 0.0)
        wf_sharpe = float(stats.get("wf_overall_sharpe", 0.0) or 0.0)
        num_trades = float(stats.get("num_trades", 0.0) or 0.0)
        final_eq = float(stats.get("final_equity", 0.0) or 0.0)

        # Group (b): dummy strategies with no trades / no edge
        is_dummy = (num_trades == 0.0 and return_pct == 0.0 and not accepted)

        # Group (a): clearly weak / bad strategies
        is_weak = (
            status in {"disabled", "candidate"}
            and not accepted
            and (
                return_pct < -3.0
                or pf < 1.0
                or wf_sharpe < 0.0
                or num_trades < 10
                or (final_eq and final_eq < 7500.0)
            )
        )

        if is_dummy or is_weak:
            pruned[name] = rec
        else:
            kept[name] = rec

    # Remove JSON files for pruned strategies
    removed_files = []
    for name in pruned.keys():
        path = GENERATED_DIR / f"{name}.json"
        if path.exists():
            try:
                path.unlink()
                removed_files.append(str(path))
            except Exception as e:
                print(f"Warning: failed to remove {path}: {e}")

    save_pool(kept)

    print("Pruning complete.")
    print(f"Total strategies before: {len(pool)}")
    print(f"Total strategies after:  {len(kept)}")
    print(f"Total pruned:           {len(pruned)}")
    print(f"JSON files removed:     {len(removed_files)}")


if __name__ == "__main__":
    prune_pool()
