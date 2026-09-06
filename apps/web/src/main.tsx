import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { initTheme } from './state/theme';
import './styles/global.css';

// Apply the persisted theme before the first paint so there is no flash of the
// wrong theme. Runs from the bundle (no inline script), keeping the CSP intact.
initTheme();

const container = document.getElementById('root');
if (container === null) {
  throw new Error('Root container #root was not found in the document.');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
