# Documentation Maintenance Guide

## Purpose

This guide exists to keep `autonomous_trading_ai` documentation aligned with the
actual codebase.

The project now has a clearer **pass 3 shape**:

- structured regime-aware routing
- explicit specialist metadata in strategy records
- stronger live gating and monitoring
- best-effort alerting / webhook plumbing
- richer operator and setup docs

Documentation should reflect what is actually implemented, not what sounds nice.

## Scope

### In scope

Top-level and module docs:

- `README.md`
- `data/README.md`
- `research/README.md`
- `strategies/README.md`
- `backtests/README.md`
- `execution/README.md`
- `scheduler/README.md`
- `risk/README.md`
- `vector_memory/README.md`
- `notifications/README.md`
- `scripts/README.md`

Operational / architectural docs:

- `docs/clio/01-OVERVIEW.md`
- `docs/clio/02-ARCHITECTURE.md`
- `docs/clio/03-DEVELOPMENT_PLAN.md`
- `docs/clio/04-IMPROVEMENT_OPPORTUNITIES.md`
- `docs/clio/05-RUNBOOK_TROUBLESHOOTING.md`
- `docs/clio/06-M15_IMPROVEMENT_ROADMAP.md`
- `docs/clio/07-ROUTING_LAYER_AUDIT_AND_TASKLIST.md`

Instructions / runbooks:

- `user_instructions/START_AUTONOMOUS_TRADING.md`
- `agent_instructions/SETUP_AUTONOMOUS_TRADING_ENVIRONMENT.md`
- `agent_instructions/AUTONOMOUS_TRADING_DEV_AGENT.md`

### Out of scope

This maintenance task should **not**:

- change trading rules
- change risk posture
- change scheduler timings just to match docs
- add new external integrations
- modify OpenClaw gateway config
- treat aspirational notes as implemented behavior

## Required Workflow

For each documentation update:

1. Read the current doc.
2. Inspect the relevant code/module structure.
3. Verify paths, filenames, artifacts, and status names.
4. Update the doc to describe **current behavior**.
5. Keep the doc useful for one of these audiences:
   - developer
   - operator
   - Clio / future agent
   - Afu as project owner

## What to Verify Against Code

When checking a module, prefer verifying:

- actual file names
- actual JSON / parquet / log artifacts
- actual config fields in `config.py`
- actual scheduler jobs in `scheduler/main.py`
- actual state/status names in strategy pool records
- actual alert paths and limitations

For pass 3 specifically, double-check whether docs reflect:

- structured regime fields
- `strategy_explain.meta` routing metadata
- live specialist gating
- exploratory vs active behavior
- open-trade / ticket-mapping state files where applicable

## Style Conventions

Use clean Markdown with practical headings like:

- `## Purpose`
- `## Scope`
- `## Key Files`
- `## How It Works`
- `## How It’s Used`
- `## Gotchas / Notes`
- `## Changelog (Docs)`

Additional conventions:

- prefer bullets over bloated paragraphs
- use repo-relative paths
- call out experimental / best-effort behavior clearly
- distinguish implemented behavior from roadmap ideas
- avoid vague claims like “fully autonomous” unless bounded by real safeguards

## Documentation Standards

Good docs in this repo should be:

- **accurate** – match the real code
- **bounded** – avoid generic trading-platform fantasy language
- **operationally useful** – help someone run, inspect, or extend the system
- **honest about limitations** – especially for alerting, backtest realism, and routing confidence

## Changelog Discipline

Every edited doc should keep a short `## Changelog (Docs)` section.

Append short entries like:

- `- 2026-03-27: Updated for pass 3 routing and live-monitoring behavior.`

Keep entries concise and factual.

## Final Check Before Commit

Before finalizing doc work:

- review `git diff`
- make sure changes are documentation-only unless explicitly requested otherwise
- ensure terms are consistent across root README, module READMEs, runbooks, and instruction files
- ensure no doc still describes obsolete behavior as current

## Changelog (Docs)

- 2026-03-27: Refreshed the maintenance guide for pass 3 and expanded scope to include architecture, runbooks, and instruction files.