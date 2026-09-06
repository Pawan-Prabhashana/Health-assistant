# 16. UI and experience polish

- Status: Accepted
- Date: 2026-09-05

## Context

Phase 7 shipped a functional, accessible, typed frontend, but it read as a tidy
scaffold rather than a designed product. Phase 10 is a focused design pass that
elevates it to a distinctive, polished, calm healthcare interface without
regressing the Phase 7–9 discipline: the OpenAPI-generated types, the typed
client, and the fetch-based SSE event contract are untouched; only the components
that consume them were restyled and reorganised.

## Decision

**Visual identity.** A small, coherent brand: an inline SVG mark (a rounded teal
tile carrying a calm heartbeat glyph, themed from the palette — no external
asset), used in the header, the landing, and as the assistant avatar in the
thread, with the "Sahana" wordmark. It is a consistent identity, not a logo
exercise.

**Tokens over ad-hoc values.** The existing token layer was extended rather than
sprinkled on: a fuller type scale (`--text-3xl`, tracking tokens), a `--space-7`,
`--radius-xl`, layered elevation (`--shadow-xs…lg`), backdrop/overlay tints, and a
single motion vocabulary — `--motion-fast/med/slow` with `--ease-out` /
`--ease-standard`. Every component styles from tokens; no inline-style soup; one
styling approach (CSS Modules) throughout.

**Motion language.** CSS-only (transitions + keyframes), quick and calm: message
rise-in, a streaming "thinking" indicator that resolves into flowing tokens with a
caret, hover/press feedback, the sidebar drawer slide, and fade-ins for notices
and empty states. No motion library was added (keeping the bundle lean and CSP
simple); the global `prefers-reduced-motion` block disables every animation and
transition and forces auto scroll.

**Theme toggle.** An explicit, persisted theme with three states — system / light
/ dark — cycled from a header control. `data-theme` on the document element
drives the token layer; "system" clears it so `prefers-color-scheme` governs, and
an explicit choice wins in both directions. The persisted theme is applied from
the bundle before first paint (`initTheme()` in the entrypoint), so there is no
flash and no inline script (the Phase 8 CSP stays intact). Both palettes are fully
designed, including elevation.

**Redesigned surfaces.** A calm "front desk" landing (brand, value framing, trust
markers, graceful privacy note); a polished session sidebar with skeleton loading,
relative timestamps, active/hover states, and reveal-on-hover delete; a centrepiece
chat thread with an assistant avatar, distinct bubbles, the route-named thinking
indicator, and autoscroll that yields when the user scrolls up; a refined composer
(pill send/stop, character hint near the cap, Enter-to-send affordance).

**Five route outcomes as first-class visuals.** CRM renders as a titled clinical
data card wrapping a real, accessible `<table>` with a toned status pill; RAG/web
citations render as source chips (document glyph + KB title; globe glyph + host +
safe external link); a cache hit keeps a quiet "answered instantly" affordance; a
refusal is a warm-neutral boundary, never alarming red; the route + latency sit in
an unobtrusive badge.

**Responsive.** Mobile-first from ~380px: the sidebar becomes an off-canvas drawer
with an overlay, opened from a header menu button; bubbles go full width, the
assistant avatar and desktop-only hints hide, tap targets stay comfortable, and no
surface scrolls horizontally.

**Optional trace panel.** An off-by-default `<details>` disclosure on a turn
surfaces the PII-free reasoning trace (node decisions, route, timings) for demos —
present only for live turns, out of the way otherwise.

## Consequences

- The app reads as deliberately designed and distinctly Sahana, in both themes and
  at phone and desktop widths, with a single motion vocabulary.
- No new runtime dependency; the bundle grew modestly (CSS ~+15KB raw / ~+2KB
  gzip, JS ~+10KB raw / ~+3KB gzip) — all from styling and small components.
- Accessibility is preserved or improved: labelled controls, visible focus, the
  polite `aria-live` streaming announcement, `prefers-reduced-motion` honoured
  everywhere, and the CRM reply remains a semantic table.
- The typed client and SSE contract are unchanged; all 16 endpoints stay wired.
