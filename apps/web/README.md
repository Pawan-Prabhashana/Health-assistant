# Sahana Web

React + Vite + TypeScript client for the Sahana hospital health assistant. In
Phase 0 the client renders a single health-status view that reads live readiness
data from the API, proving the browser → nginx → api request path end to end.

## Requirements

- Node.js 20 or newer
- npm

## Setup

```bash
npm install
```

## Development

```bash
npm run dev
```

The dev server listens on port 8080 and proxies `/api/*` to the FastAPI backend
on `http://localhost:8000`, mirroring the nginx reverse proxy used in
production. Start the API separately (see [`apps/api`](../api/README.md)).

## Build

```bash
npm run build      # type-check with tsc, then bundle with Vite into dist/
npm run preview    # serve the production build on port 8080
```

## Quality gates

```bash
npm run lint          # ESLint (flat config, type-checked rules)
npm run format:check  # Prettier
```

## Layout

```
src/
  main.tsx                     # React entrypoint
  App.tsx                      # top-level layout
  index.css                    # theming and component styles
  api/
    client.ts                  # typed fetch wrapper rooted at /api
    health.ts                  # typed bindings for the health endpoints
  components/
    HealthStatus.tsx           # renders readiness and dependency checks
```
