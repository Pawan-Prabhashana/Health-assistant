// TanStack Query hooks over the typed client: server-state reads (patient
// resolution, sessions, history, health/config) and the mutations that create,
// delete, and manage them, with cache invalidation wired to keep the UI
// consistent after each write.

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { api } from '../api/client';
import type {
  ChatHistoryResponse,
  ConfigResponse,
  LivenessResponse,
  PatientResponse,
  ReadinessResponse,
  SessionDetailResponse,
  SessionResponse,
  SummarizeResponse,
} from '../api/types';
import { queryKeys } from './keys';

export function usePatientByPhone(phone: string | null): UseQueryResult<PatientResponse> {
  return useQuery({
    queryKey: phone ? queryKeys.patientByPhone(phone) : ['patient', 'by-phone', 'none'],
    queryFn: ({ signal }) => api.getPatientByPhone(phone as string, signal),
    enabled: phone !== null,
  });
}

export function usePatientById(patientId: string | null): UseQueryResult<PatientResponse> {
  return useQuery({
    queryKey: patientId ? queryKeys.patientById(patientId) : ['patient', 'by-id', 'none'],
    queryFn: ({ signal }) => api.getPatientById(patientId as string, signal),
    enabled: patientId !== null,
  });
}

export function useUpsertPatient(): UseMutationResult<
  PatientResponse,
  Error,
  { phone: string; fullName?: string }
> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ phone, fullName }) => api.upsertPatient({ phone, full_name: fullName ?? null }),
    onSuccess: (patient) => {
      client.setQueryData(queryKeys.patientByPhone(patient.phone), patient);
      client.setQueryData(queryKeys.patientById(patient.id), patient);
    },
  });
}

export function useDeletePatient(): UseMutationResult<void, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patientId) => api.deletePatient(patientId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['patient'] });
      void client.invalidateQueries({ queryKey: ['sessions'] });
    },
  });
}

export function useSessions(phone: string | null): UseQueryResult<SessionResponse[]> {
  return useQuery({
    queryKey: phone ? queryKeys.sessions(phone) : ['sessions', 'none'],
    queryFn: ({ signal }) => api.listSessions({ phone: phone as string }, signal),
    enabled: phone !== null,
  });
}

export function useSession(sessionId: string | null): UseQueryResult<SessionDetailResponse> {
  return useQuery({
    queryKey: sessionId ? queryKeys.session(sessionId) : ['session', 'none'],
    queryFn: ({ signal }) => api.getSession(sessionId as string, undefined, signal),
    enabled: sessionId !== null,
  });
}

export function useCreateSession(
  phone: string | null,
): UseMutationResult<SessionResponse, Error, { title?: string }> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ title }) => api.createSession({ phone: phone ?? null, title: title ?? null }),
    onSuccess: () => {
      if (phone !== null) {
        void client.invalidateQueries({ queryKey: queryKeys.sessions(phone) });
      }
    },
  });
}

export function useDeleteSession(phone: string | null): UseMutationResult<void, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sessionId) => api.deleteSession(sessionId),
    onSuccess: () => {
      if (phone !== null) {
        void client.invalidateQueries({ queryKey: queryKeys.sessions(phone) });
      }
    },
  });
}

export function useHistory(sessionId: string | null): UseQueryResult<ChatHistoryResponse> {
  return useQuery({
    queryKey: sessionId ? queryKeys.history(sessionId) : ['history', 'none'],
    queryFn: ({ signal }) => api.getHistory({ session_id: sessionId as string }, signal),
    enabled: sessionId !== null,
  });
}

export function useSummarize(): UseMutationResult<SummarizeResponse, Error, string> {
  return useMutation({
    mutationFn: (sessionId) => api.summarize(sessionId),
  });
}

export function useClearMemory(): UseMutationResult<void, Error, string> {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sessionId) => api.clearMemory(sessionId),
    onSuccess: (_data, sessionId) => {
      void client.invalidateQueries({ queryKey: queryKeys.history(sessionId) });
    },
  });
}

export function useReadiness(enabled = true): UseQueryResult<ReadinessResponse> {
  return useQuery({
    queryKey: queryKeys.readiness(),
    queryFn: ({ signal }) => api.getReadiness(signal),
    enabled,
    refetchInterval: enabled ? 20_000 : false,
  });
}

export function useLiveness(enabled = true): UseQueryResult<LivenessResponse> {
  return useQuery({
    queryKey: queryKeys.liveness(),
    queryFn: ({ signal }) => api.getLiveness(signal),
    enabled,
    refetchInterval: enabled ? 20_000 : false,
  });
}

export function useConfig(enabled = true): UseQueryResult<ConfigResponse> {
  return useQuery({
    queryKey: queryKeys.config(),
    queryFn: ({ signal }) => api.getConfig(signal),
    enabled,
    staleTime: 5 * 60_000,
  });
}
