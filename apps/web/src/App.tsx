import { HealthStatus } from './components/HealthStatus';

export function App(): React.JSX.Element {
  return (
    <main className="app">
      <header className="app__header">
        <h1>Sahana</h1>
        <p className="app__tagline">Hospital health assistant</p>
      </header>
      <section className="app__panel">
        <h2>Backend status</h2>
        <HealthStatus />
      </section>
    </main>
  );
}
