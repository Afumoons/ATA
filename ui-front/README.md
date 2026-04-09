# UI Frontend — Operator UI v1

Read-only Next.js operator dashboard for `autonomous_trading_ai`.

## Design direction

The frontend follows a restrained premium dashboard direction inspired mainly by the calmer operator-facing cues in `awesome-design-md`, especially the clarity and surface discipline of references like Linear, IBM, and Revolut:

- typography-first hierarchy
- low-noise surfaces
- calm blue accenting instead of neon trading visuals
- generous spacing and strong readability
- coherent dark and light themes

## Routes

- `/` — Overview
- `/execution` — Execution Diagnostics
- `/pool` — Pool Overview
- `/manifest` — Manifest Viewer
- `/audit` — Audit Timeline

## Requirements

- Node.js 20+
- npm

## Install

```bash
npm install
```

## Run locally

```bash
npm run dev
```

Default dev URL:

- `http://localhost:3000`

## Production build verification

```bash
npm run build
npm run start
```

## Healthy-backend QA pass

Once the read-only UI API is running and the frontend is serving locally, run:

```bash
set UI_API_BASE=http://127.0.0.1:8010/api
set UI_FRONT_BASE=http://127.0.0.1:3000
npm run qa:healthy-backend
```

What it checks:

- the UI API health endpoint responds
- overview, execution, pool, manifest, strategy, and audit payloads parse and expose the expected operator-facing fields
- the primary frontend routes return healthy HTML shells

This gives a repeatable basic QA pass for the final Phase 1 reliability checkbox.

## Backend API configuration

The UI expects the backend UI API base URL via:

- `NEXT_PUBLIC_UI_API_BASE`

If unset, it defaults to:

- `/api`

Example:

```bash
set NEXT_PUBLIC_UI_API_BASE=http://localhost:8010/api
npm run dev
```

## Notes

- The older `ui/` frontend is legacy/reference only.
- This app is intentionally read-only.
- Theme preference is stored locally in the browser and can be toggled from the sidebar.
- For the roadmap completion sweep, use `npm run qa:healthy-backend` after the API and frontend are both up.
