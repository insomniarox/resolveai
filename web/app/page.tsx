import { InvestigationWorkspace } from "@/components/investigation-workspace";

export default function Home() {
  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">AI incident investigation copilot</p>
          <h1>ResolveAI</h1>
        </div>
        <p className="page-introduction">
          Review synthetic operational evidence, investigate an incident, and
          inspect the supported conclusion.
        </p>
      </header>

      <InvestigationWorkspace />
    </main>
  );
}
