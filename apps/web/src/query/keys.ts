// Centralised query keys so cache reads, writes, and invalidations stay
// consistent. Each key is a stable tuple; hooks and mutations reference these
// rather than repeating string arrays.

export const queryKeys = {
  patientByPhone: (phone: string) => ['patient', 'by-phone', phone] as const,
  patientById: (patientId: string) => ['patient', 'by-id', patientId] as const,
  sessions: (phone: string) => ['sessions', phone] as const,
  session: (sessionId: string) => ['session', sessionId] as const,
  history: (sessionId: string) => ['history', sessionId] as const,
  readiness: () => ['health', 'readiness'] as const,
  liveness: () => ['health', 'liveness'] as const,
  config: () => ['config'] as const,
} as const;
