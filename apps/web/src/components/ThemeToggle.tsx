import { useThemeStore, type Theme } from '../state/theme';
import styles from './ThemeToggle.module.css';

const LABELS: Record<Theme, string> = {
  system: 'System theme',
  light: 'Light theme',
  dark: 'Dark theme',
};

const NEXT: Record<Theme, Theme> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
};

function ThemeIcon({ theme }: { theme: Theme }): React.JSX.Element {
  if (theme === 'light') {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none">
        <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.8" />
        <path
          d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5 5l1.4 1.4M17.6 17.6L19 19M19 5l-1.4 1.4M6.4 17.6L5 19"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (theme === 'dark') {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none">
        <path
          d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none">
      <rect x="3" y="5" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

// A compact control that cycles system → light → dark, persisted. The label
// names the current theme and the next action for screen readers.
export function ThemeToggle(): React.JSX.Element {
  const theme = useThemeStore((state) => state.theme);
  const cycle = useThemeStore((state) => state.cycle);

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={cycle}
      title={`${LABELS[theme]} — switch to ${LABELS[NEXT[theme]].toLowerCase()}`}
      aria-label={`${LABELS[theme]}. Activate to switch to ${LABELS[NEXT[theme]].toLowerCase()}.`}
    >
      <ThemeIcon theme={theme} />
    </button>
  );
}
