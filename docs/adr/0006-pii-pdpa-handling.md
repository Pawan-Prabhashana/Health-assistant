# 6. PII and PDPA handling

- Status: Accepted
- Date: 2026-08-26

## Context

Sahana stores phone numbers and names, which are personal data under Sri Lanka's
Personal Data Protection Act (PDPA No. 9 of 2022). The system must avoid leaking
that data through logs, list responses, or error messages, and must be able to
erase a person's data on request. Phase 1 establishes this posture before any
chat data accumulates.

## Decision

**Log redaction.** A structlog processor (`redact_pii`) masks the values of
sensitive event keys (`phone`, `full_name`, `name`, extensible via
`mark_sensitive`) to `[redacted]` in every environment, in both the structlog and
stdlib-bridge chains. The convention is to pass PII only as structured fields,
never interpolated into a message string, so the processor can always find and
mask it. A test asserts that a log event carrying a phone and name emits neither
raw value.

**Data minimization in responses.** List and aggregate responses never include
`phone` or `full_name`. Session list responses carry only the opaque
`patient_id`. Only a single-record patient response (the patient's own identity)
returns `phone` and `full_name`. Error responses carry a stable code and a
generic message and never echo submitted values, so an invalid phone can never be
reflected back in an error body.

**Right to erasure.** `DELETE /patients/{id}` hard-deletes the patient row.
`ON DELETE CASCADE` foreign keys remove the patient's appointments, sessions, and
messages in the same transaction. The delete is a genuine removal, not a soft
flag. A test creates a patient with a session and appointment, deletes the
patient, and asserts the dependent rows are gone.

## Consequences

- Personal data does not reach logs regardless of log level or environment.
- The API surface cannot be used to enumerate patients or harvest names/phones.
- A PDPA erasure request is satisfied by a single endpoint with cascading effect.
- The redaction is key-based; engineers must follow the "PII as structured
  fields" convention. This is documented in `docs/data-handling.md` and enforced
  by review and the redaction test.
