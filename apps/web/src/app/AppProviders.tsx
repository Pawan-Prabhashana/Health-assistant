import { useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';

import { createQueryClient } from '../query/client';

interface AppProvidersProps {
  children: React.ReactNode;
}

// Wires the app-wide providers. The QueryClient is created once per mount via
// lazy state so a re-render never discards the cache.
export function AppProviders({ children }: AppProvidersProps): React.JSX.Element {
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
