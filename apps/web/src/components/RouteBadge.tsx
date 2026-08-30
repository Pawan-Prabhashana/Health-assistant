import { routeLabel } from '../lib/format';
import type { Route } from '../api/types';
import styles from './RouteBadge.module.css';

interface RouteBadgeProps {
  route: string | null;
  cached?: boolean;
}

// A single, quiet chip naming the path the answer took. The route drives the
// accent colour via a data attribute; a cache hit is shown as its own subtle
// variant rather than an extra badge.
export function RouteBadge({ route, cached = false }: RouteBadgeProps): React.JSX.Element {
  const key: Route | 'refusal' | 'cache' = cached
    ? 'cache'
    : route === null
      ? 'refusal'
      : (route as Route);
  const label = cached ? 'Answered instantly' : routeLabel(route);
  return (
    <span className={styles.badge} data-kind={key}>
      {label}
    </span>
  );
}
