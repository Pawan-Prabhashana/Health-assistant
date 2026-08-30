// Global test setup: jest-dom matchers and the MSW server lifecycle. The server
// intercepts fetch so every test runs against mocked API endpoints without a
// backend. `onUnhandledRequest: 'error'` keeps tests honest — an un-mocked call
// fails loudly rather than hitting the network.

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { server } from './server';

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});
