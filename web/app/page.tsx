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
          Investigate an incident, inspect its evidence, or compare OpenRouter and
          Jev on the same candidate hypotheses.
        </p>
      </header>

      <InvestigationModeWorkspace />
    </main>
  );
}
