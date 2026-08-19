import { InvestigationModeWorkspace } from "@/components/investigation-mode-workspace";

export default function Home() {
  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">AI incident investigation copilot</p>
          <h1>ResolveAI</h1>
        </div>
        <p className="page-introduction">
          Follow the prepared synthetic demo or submit one runtime incident
          bundle, then inspect a transient result or compare two explicitly saved
          provenance snapshots.
        </p>
      </header>

      <InvestigationModeWorkspace />
    </main>
  );
}
