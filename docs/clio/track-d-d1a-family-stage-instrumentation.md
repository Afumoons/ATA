# Track D1a — Family stage instrumentation

## What changed

`job_research_strategies()` now tracks per-family counts through the main research funnel:

- `generated`
- `cheap_prescreen_pass` / `cheap_prescreen_fail`
- `backtest_pass` / `backtest_fail`
- `wf_pass` / `wf_fail`
- `mc_pass` / `mc_fail`
- `accepted`
- final status buckets: `candidate`, `exploratory`, `active`

It also records skip reasons grouped by family, with up to 3 compact samples per reason.

## Output locations

### Logs

Every research cycle now emits a compact family-stage summary log:

```text
Research family-stage summary for XAUUSDm M15: {
  "ma_trend": {
    "generated": 18,
    "cp_pass": 9,
    "cp_fail": 9,
    "bt_pass": 4,
    "bt_fail": 5,
    "wf_pass": 2,
    "wf_fail": 2,
    "mc_pass": 1,
    "mc_fail": 1,
    "accepted": 1,
    "candidate": 0,
    "exploratory": 1,
    "active": 0
  }
}
```

This is meant for quick bottleneck spotting inside scheduler logs.

### JSON artifacts

For the three Track D core-focus symbols, the same cycle writes a structured artifact to:

- `tmp/research_family_stage_summaries/XAUUSDm_M15.json`
- `tmp/research_family_stage_summaries/BTCUSDm_M15.json`
- `tmp/research_family_stage_summaries/XAGUSDm_M15.json`

Schema:

```json
{
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "generated_at": "2026-04-05T00:00:00Z",
  "families": {
    "ma_trend": {
      "stages": {
        "generated": 18,
        "cheap_prescreen_pass": 9,
        "cheap_prescreen_fail": 9,
        "backtest_pass": 4,
        "backtest_fail": 5,
        "wf_pass": 2,
        "wf_fail": 2,
        "mc_pass": 1,
        "mc_fail": 1,
        "accepted": 1,
        "candidate": 0,
        "exploratory": 1,
        "active": 0
      },
      "skip_reasons": {
        "cheap_prescreen": 9,
        "weak_wf_sharpe": 2,
        "mc_loss_prob_too_high": 1
      },
      "skip_samples": {
        "cheap_prescreen": ["strat_a:tr=0,pf=0.00,sh=0.00,dd=0.0"],
        "weak_wf_sharpe": ["strat_b:0.081"]
      }
    }
  }
}
```

## Why JSON + log

- **Log** = fast visual bottleneck scan during a live run.
- **JSON artifact** = stable input for Track D2/D3 diagnosis and before/after comparisons.

Artifacts now cover the full Track D core-focus universe (XAU/BTC/XAG) while staying limited to those symbols so the repair track remains compact and comparable.
