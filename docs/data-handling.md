# Data handling

How Sahana treats personal data. The governing decision is
[ADR 0006](adr/0006-pii-pdpa-handling.md); this page is the operational summary.

## What is personal data here

Under Sri Lanka's PDPA, both the **phone number** and the **full name** of a
patient are personal data. Sahana stores:

| Data                     | Where            | Why                                    |
| ------------------------ | ---------------- | -------------------------------------- |
| Phone number (E.164)     | `patients.phone` | Identity key; how a caller is resolved |
| Full name                | `patients.full_name` | Shown in the patient's own CRM view |
| Medical record number    | `patients.mrn`   | Human-readable record ID (`P-10023`)   |
| Clinical status          | `patients.status`| CRM reply                              |
| Appointments             | `appointments`   | CRM context                            |
| Conversation threads     | `sessions`       | Linked to a patient by opaque id       |
| Messages                 | `messages`       | Conversation content (later phase)     |

No secrets, credentials, or real personal data are stored in the repository or
in seed data.

## Data minimization

- **List and aggregate responses never return `phone` or `full_name`.** Session
  lists expose only the opaque `patient_id`.
- **Single-record identity only.** `phone` and `full_name` appear only in a
  single patient record fetched by that patient's own identity.
- **Errors never echo input.** Error responses use a stable code and a generic
  message; an invalid phone number is never reflected back.

## Log redaction

- A structlog processor masks the values of sensitive keys (`phone`,
  `full_name`, `name`) to `[redacted]` in every environment.
- **Convention:** pass PII only as structured log fields
  (`logger.info("event", phone=...)`), never interpolated into the message
  string. Interpolated values cannot be redacted.
- Extend the sensitive set with `sahana_api.logging.mark_sensitive(...)` when new
  personal fields are introduced.
- A test (`tests/test_logging_redaction.py`) asserts raw phone and name never
  appear in emitted logs.

## Right to erasure (PDPA)

`DELETE /patients/{id}` performs a **hard delete**:

1. The `patients` row is removed.
2. `ON DELETE CASCADE` removes the patient's `appointments`, `sessions`, and
   `messages` in the same transaction.

There is no soft-delete flag and no retained shadow copy. Erasure is verified by
`tests/test_patients_api.py::test_delete_patient_cascades_sessions` and
`tests/test_repositories.py::test_patient_delete_cascades`.

## Transport and storage notes

- Phone numbers are normalized to E.164 before storage, so there is one canonical
  representation per person.
- All timestamps are stored as `timestamptz` in UTC.
- Personal data is never placed in URLs beyond the deliberate
  `GET /patients/by-phone/{phone}` identity lookup, and never in query strings for
  list endpoints (which filter by phone via an explicit, validated parameter).
