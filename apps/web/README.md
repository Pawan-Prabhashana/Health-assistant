# Sahana Web

React + Vite + TypeScript client for the Sahana hospital health assistant. It is
the full chat experience over the Phase 0–6 backend: phone identity, session
management, streaming chat (fetch-based SSE), the CRM table, RAG/web citations,
and the refusal / cache-hit / tool-backed states — typed end to end against the
backend's OpenAPI schema, accessible, and tested. See
[ADR 0013](../../docs/adr/0013-frontend-architecture.md).

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

The dev server listens on port 3000 and proxies `/api/*` to the FastAPI backend
on `http://localhost:8000`, mirroring the nginx reverse proxy used in
production. Start the API separately (see [`apps/api`](../api/README.md)).

## API types (generated, anti-drift)

TypeScript types are generated from the backend's OpenAPI schema — never
hand-written — so the client cannot silently drift from the Pydantic models.

```bash
npm run gen:api    # openapi.json -> src/api/schema.d.ts
```

`openapi.json` is a committed snapshot of the backend schema, so generation is
deterministic and needs no running backend. To refresh it after a backend change,
export the schema again and rerun `gen:api`:

```bash
# with the API running (directly or through the proxy):
curl http://localhost:8000/openapi.json -o openapi.json
npm run gen:api
```

`src/api/types.ts` aliases the generated component schemas; `src/api/client.ts`
calls all sixteen endpoints through them; `src/api/sse.ts` is the fetch-based SSE
client for `POST /chat/stream` (`EventSource` is GET-only and cannot carry the
request body).

## Build

```bash
npm run build      # type-check with tsc, then bundle with Vite into dist/
npm run preview    # serve the production build on port 3000
```

## Quality gates

```bash
npm run lint          # ESLint (flat config, type-checked rules)
npm run format:check  # Prettier
npm run test          # Vitest + React Testing Library + MSW
npm run test:coverage # with a V8 coverage report
```

## Layout

```
src/
  main.tsx                     # React entrypoint
  App.tsx                      # app shell: identity gate, workspace, views
  app/AppProviders.tsx         # QueryClientProvider
  api/
    schema.d.ts                # GENERATED from openapi.json (do not edit)
    types.ts                   # aliases over the generated schemas
    client.ts                  # typed client for all 16 endpoints
    sse.ts                     # fetch-based SSE client + pure frame parser
  state/                       # Zustand stores: identity (persisted), session/view, theme (persisted)
  query/                       # TanStack Query client, keys, and hooks
  hooks/useChatStream.ts       # per-session send/stream controller
  lib/                         # phone validation, formatting, assistant view model
  components/                  # design-system components (CSS Modules); Logo, ThemeToggle, TracePanel
  styles/                      # design tokens + global base styles
  test/                        # MSW server, handlers, fixtures, render helper
```

## Design system and accessibility

Styling is CSS Modules over a design-token layer (`src/styles/tokens.css`): a
calm clinical palette, a refined type/space scale, layered elevation, and a single
CSS-only motion vocabulary (see [ADR 0016](../../docs/adr/0016-ui-experience-polish.md)).
Theming has three states — system / light / dark — via a persisted header toggle
that sets `data-theme` on the document (applied before first paint, no inline
script); both palettes are fully designed. The layout is mobile-first: the sidebar
collapses to an off-canvas drawer at ~380px.

Accessibility stays first-class: keyboard navigation, visible focus, WCAG AA
contrast, labelled controls, a real CRM `<table>`, a polite `aria-live` region
that announces the completed streamed answer, and `prefers-reduced-motion`
honoured for every animation. The five route outcomes each have a distinct
treatment — CRM data card, KB/web citation chips, cache-hit affordance, calm
refusal boundary, and an unobtrusive route + latency badge.
