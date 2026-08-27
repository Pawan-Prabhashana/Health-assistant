# 5. Data model and phone-based identity

- Status: Accepted
- Date: 2026-08-26

## Context

Sahana recognizes callers and stores their clinical context and conversation
history. We must choose an identity key, a human-readable record number for the
CRM view, how conversation threads relate to identity, and how to represent
enumerated states consistently across the ORM and API layers.

## Decision

**Phone number is the identity key.** A patient is uniquely identified by their
phone number, stored in canonical E.164 form. All inbound numbers are normalized
on the way in (default region Sri Lanka, `+94`) so `0771234567`,
`077 123 4567`, and `+94771234567` resolve to the same patient. `POST /patients`
is an upsert on phone; `GET /patients/by-phone/{phone}` is how the chat layer
will recognize a caller.

**MRN scheme.** Each patient also has a human-readable medical record number
(`mrn`, e.g. `P-10023`) — the "Patient ID" shown in the CRM table. MRNs are
allocated by a Postgres sequence (`patient_mrn_seq`, `START WITH 10023`) via the
column default `'P-' || nextval('patient_mrn_seq')`. Allocation follows insertion
order, so a fresh seed reproduces the slide's IDs (John Doe → `P-10023`). A
patient created without a name (an anonymous caller known only by phone) is stored
with the placeholder name `Unknown`; a later request that supplies a name updates
it.

**Sessions may be anonymous.** A conversation `session.patient_id` is nullable: a
thread can begin before the caller identifies themselves, and the chat layer
associates it once the phone resolves. Messages exist as a table now (written by
a later phase) so the schema is stable; the reserved `metadata` JSONB column
holds route/latency/token accounting later.

**Enums are defined once.** Each enumerated state (`patient.status`,
`appointment.status`, `message.role`) is a Python `enum.StrEnum` whose values are
the exact Postgres enum labels, materialized as native Postgres enum types. The
single definition is imported by both the ORM models and the Pydantic schemas, so
the two layers cannot drift.

**Cascade.** Appointments, sessions, and messages are owned by their parent via
`ON DELETE CASCADE` foreign keys with matching ORM relationships, so deleting a
patient removes all of their data (see ADR 0006).

## Consequences

- The chat layer has a stable, normalized identity key and never has to reconcile
  phone-number formats.
- MRNs are readable and demo-reproducible without a separate ID service.
- Nullable session identity models the real conversation flow (identify mid-thread)
  without a schema change later.
- Sequence-allocated MRNs are ordering-dependent; this is documented and only
  matters for reproducing demo data on a fresh database.
