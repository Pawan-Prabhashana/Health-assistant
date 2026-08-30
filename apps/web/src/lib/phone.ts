// Lightweight client-side phone validation. The backend is the authority: it
// normalises to E.164 with libphonenumber and rejects invalid numbers with a 422
// envelope. This check only gives immediate feedback before a request is sent, so
// it is intentionally permissive — it accepts the local (Sri Lanka) and
// international formats the backend can normalise, and rejects obvious junk.

const DIGITS = /\d/g;

/** Return true when `value` looks like a plausible phone number to submit. */
export function isPlausiblePhone(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed === '') {
    return false;
  }
  // Only digits, spaces, and the grouping characters people actually type.
  if (!/^\+?[\d\s()-]+$/.test(trimmed)) {
    return false;
  }
  const digitCount = (trimmed.match(DIGITS) ?? []).length;
  // National numbers run ~9-10 digits; international with country code up to 15.
  return digitCount >= 9 && digitCount <= 15;
}
