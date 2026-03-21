# Documentation Maintenance Guide

## Scope

Background agent task: keep documentation for `autonomous_trading_ai` in sync with the current codebase.

### In scope

- High-level system overview: `README.md` in repo root.
- Per-module docs:
  - `data/README.md`
  - `research/README.md`
  - `strategies/README.md`
  - `backtests/README.md`
  - `execution/README.md`
  - `scheduler/README.md`
  - `risk/README.md`
  - `vector_memory/README.md`
  - `notifications/README.md` (experimental outbound alerts)
- Instruction/runbook docs:
  - `user_instructions/START_AUTONOMOUS_TRADING.md`
  - `agent_instructions/SETUP_AUTONOMOUS_TRADING_ENVIRONMENT.md` (if present)

### Out of scope (for this agent)

- Changing core trading logic or risk parameters.
- Creating new external integrations (e.g., WhatsApp Cloud API).
- Modifying OpenClaw gateway config.
- Anything that changes live trading behavior.

## Responsibilities

For each module in scope:

1. **Read existing README/instructions**.
2. **Scan relevant code** in that module for changes that affect:
   - public APIs (functions/classes meant to be used by other modules),
   - file layouts (paths, JSON/Parquet filenames),
   - runtime flow (which jobs call what, and when),
   - configuration (env vars, config dataclasses, defaults).
3. **Update docs** so they accurately describe current behavior.
4. Keep docs:
   - concise and technical,
   - focused on what a developer/operator needs to know,
   - version-agnostic (avoid hardcoding dates or ephemeral TODOs).

## Conventions

- Use Markdown headings like `## Purpose`, `## Key Files`, `## How Its Used`, `## Gotchas / Notes`.
- Prefer bullet lists over long paragraphs.
- When describing paths, use repo-relative paths (e.g. `execution/trades.log`).
- When documenting env vars, show example values and explain defaults.
- When behavior is experimental or partially wired, label it clearly (e.g. notifications).

## Safety

- Do not alter trading rules, risk logic, or scheduler timing from this agent.
- Do not add new external network calls or API clients.
- Only read and write documentation files and code for the purpose of updating docs.

## Check-in

- Leave a short summary of changes at the bottom of each edited README under a `## Changelog (Docs)` section, appending entries like:
  - `- 2026-03-20: Updated for new notifications module and research memory details.`

This keeps doc evolution visible without touching functional code.
