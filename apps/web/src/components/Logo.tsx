import logoUrl from '../assets/Sahana Logo.png';
import styles from './Logo.module.css';

interface LogoProps {
  /** Mark size in pixels. */
  size?: number;
  /** Render the "Sahana" wordmark beside the mark. */
  withWordmark?: boolean;
}

// The Sahana brand mark: the project logo (Sahana Logo.png), the same artwork the
// README uses. Rendered as an <img> so it stays crisp; the source is bundled by
// Vite (hashed, same-origin), so it satisfies the app's img-src 'self' CSP.
export function Logo({ size = 28, withWordmark = false }: LogoProps): React.JSX.Element {
  return (
    <span className={styles.logo}>
      <img className={styles.mark} src={logoUrl} width={size} height={size} alt="Sahana" />
      {withWordmark && <span className={styles.wordmark}>Sahana</span>}
    </span>
  );
}
