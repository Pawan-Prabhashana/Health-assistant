// The shared TanStack Query client. Retries are disabled for 4xx client errors
// (a 404 for a deleted session should surface immediately, not after retries)
// and kept modest otherwise; server state is considered fresh briefly to avoid
// refetch storms while the user works within a session.

import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '../api/client';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}
