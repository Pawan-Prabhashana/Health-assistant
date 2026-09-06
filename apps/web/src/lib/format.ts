// Small pure formatting helpers shared across components.

import type { Route, Verdict } from '../api/types';

/** Human-readable latency, e.g. `290 ms` or `2.4 s`. */
export function formatLatency(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)} ms`;
  }
  return `${(ms / 1000).toFixed(1)} s`;
}

/** A short, human timestamp for a message bubble. */
export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** A compact relative time for the session list, e.g. `just now`, `3h`, `2d`. */
export function formatRelative(iso: string): string {
  const date = new Date(iso);
  const ms = Date.now() - date.getTime();
  if (Number.isNaN(ms)) {
    return '';
  }
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) {
    return 'just now';
  }
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d`;
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export interface CitationSource {
  kind: 'web' | 'kb';
  label: string;
  href: string | null;
}

/** Classify a citation as a web URL (host as label) or a KB document title. */
export function citationSource(value: string): CitationSource {
  if (/^https?:\/\//i.test(value)) {
    try {
      const url = new URL(value);
      return { kind: 'web', label: url.hostname.replace(/^www\./, ''), href: value };
    } catch {
      return { kind: 'web', label: value, href: value };
    }
  }
  return { kind: 'kb', label: value, href: null };
}

const ROUTE_LABELS: Record<Route, string> = {
  crm: 'Your records',
  rag: 'Knowledge base',
  web_search: 'Web search',
  direct: 'Concierge',
};

/** Display label for a route value; falls back to the raw value if unknown. */
export function routeLabel(route: string | null): string {
  if (route === null) {
    return 'Refusal';
  }
  return ROUTE_LABELS[route as Route] ?? route;
}

/** The in-flight message shown while the router decides / a tool runs. */
export function routingMessage(route: Route | null): string {
  switch (route) {
    case 'crm':
      return 'Checking your records…';
    case 'rag':
      return 'Searching the knowledge base…';
    case 'web_search':
      return 'Searching the web…';
    case 'direct':
      return 'Composing a reply…';
    default:
      return 'Thinking…';
  }
}

/** Coarse answer kind, used to pick the calm/cache/tool visual treatment. */
export function answerKind(verdict: Verdict): 'refusal' | 'cache' | 'answer' {
  switch (verdict) {
    case 'out_of_scope':
      return 'refusal';
    case 'cache_hit':
      return 'cache';
    default:
      return 'answer';
  }
}
