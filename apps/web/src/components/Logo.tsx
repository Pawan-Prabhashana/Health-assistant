import styles from './Logo.module.css';

interface LogoProps {
  /** Mark size in pixels. */
  size?: number;
  /** Render the "Sahana" wordmark beside the mark. */
  withWordmark?: boolean;
}

// The Sahana brand: a rounded teal tile carrying a calm heartbeat glyph — a
// clinical, trustworthy mark drawn inline (no external asset) so it themes with
// the palette and stays crisp at any size.
export function Logo({ size = 28, withWordmark = false }: LogoProps): React.JSX.Element {
  return (
    <span className={styles.logo}>
      <svg
        className={styles.mark}
        width={size}
        height={size}
        viewBox="0 0 32 32"
        role="img"
        aria-label="Sahana"
      >
        <rect className={styles.tile} x="0" y="0" width="32" height="32" rx="8" />
        <path
          className={styles.pulse}
          d="M6 17.5h4l2.2-5.5 3.4 9 2.2-5 1.4 2h4.4"
          fill="none"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {withWordmark && <span className={styles.wordmark}>Sahana</span>}
    </span>
  );
}
