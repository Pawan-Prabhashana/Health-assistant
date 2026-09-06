// Theme state: the viewer's explicit light/dark choice, or "system" to follow
// the OS via prefers-color-scheme. Persisted so the choice survives reloads.
// Applying the theme sets (or clears) data-theme on the document element, which
// the token layer keys off; "system" clears the attribute so the media query
// governs. Applied at module load and on every change so there is no flash of
// the wrong theme before React mounts.

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Theme = 'system' | 'light' | 'dark';

const ORDER: Theme[] = ['system', 'light', 'dark'];

export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') {
    return;
  }
  const root = document.documentElement;
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  cycle: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      cycle: () => {
        const next = ORDER[(ORDER.indexOf(get().theme) + 1) % ORDER.length];
        applyTheme(next);
        set({ theme: next });
      },
    }),
    {
      name: 'sahana.theme',
      onRehydrateStorage: () => (state) => {
        if (state) {
          applyTheme(state.theme);
        }
      },
    },
  ),
);

/** Apply the persisted theme immediately (called from the entrypoint on boot). */
export function initTheme(): void {
  applyTheme(useThemeStore.getState().theme);
}
