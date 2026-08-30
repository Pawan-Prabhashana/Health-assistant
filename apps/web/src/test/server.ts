import { setupServer } from 'msw/node';

import { defaultHandlers } from './handlers';

// The shared MSW server used across the test suite. Tests append or override
// handlers with `server.use(...)`; `setup.ts` resets them after each test.
export const server = setupServer(...defaultHandlers);
