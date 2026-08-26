# 1. Record architecture decisions

- Status: Accepted
- Date: 2026-08-26

## Context

This project is built in ten phases by multiple contributors and is reviewed as
a portfolio-grade production system. Decisions made early (stack, topology,
conventions) constrain every later phase. Without a durable record, the rationale
behind those decisions is lost and re-litigated, and reviewers cannot tell an
intentional choice from an accident.

## Decision

We record notable architectural decisions as Architecture Decision Records
(ADRs), following Michael Nygard's format. Each ADR is a short Markdown file in
`docs/adr/`, numbered sequentially (`NNNN-title.md`), and contains Context,
Decision, and Consequences sections plus a status and date.

An ADR is written when a decision is hard to reverse, affects more than one
component, or would otherwise prompt a "why is it done this way?" question later.
ADRs are immutable once accepted; a superseding decision gets a new ADR that
references the one it replaces.

## Consequences

- The reasoning behind structural choices is discoverable in the repository.
- Reviewers and future contributors can distinguish deliberate constraints from
  incidental ones.
- There is a small, ongoing cost to writing an ADR when a significant decision is
  made; this is accepted as the price of a legible history.
