"use client";

import { useEffect, useRef, useState } from "react";

type Runbook = {
  id: string;
  title: string;
  service: string;
  content: string;
  ready: boolean;
};

async function loadRunbooks(signal?: AbortSignal): Promise<Runbook[]> {
  const response = await fetch("/api/runbooks", { cache: "no-store", signal });
  if (!response.ok) throw new Error("Runbook library could not be loaded.");
  return response.json();
}

export function RunbookLibrary({
  disabled,
  onChange,
}: {
  disabled: boolean;
  onChange: () => void;
}) {
  const [runbooks, setRunbooks] = useState<Runbook[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [service, setService] = useState("");
  const [content, setContent] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [message, setMessage] = useState("");
  const fileVersion = useRef(0);
  async function refresh() {
    setRunbooks(await loadRunbooks());
  }
  useEffect(() => {
    const abort = new AbortController();
    loadRunbooks(abort.signal)
      .then(setRunbooks)
      .catch(() => {
        if (!abort.signal.aborted)
          setError("Runbook library could not be loaded.");
      });
    return () => abort.abort();
  }, []);
  return (
    <section
      className="panel runbook-library"
      aria-labelledby="runbook-library-heading"
    >
      <div className="panel-heading">
        <h2 id="runbook-library-heading">Official runbook library</h2>
        <span className="count-summary">
          {runbooks
            ? `${runbooks.length} runbooks · ${runbooks.filter((r) => r.ready).length} searchable`
            : "Library not loaded"}
        </span>
      </div>
      <p className="comparison-note">
        Runbooks describe official procedures and expected system behavior. They
        persist across incidents. Attachments are temporary context for one
        incident. Applicable runbooks take precedence for procedure guidance;
        observed facts determine the assessment. Neither reference type has a
        numeric importance weight.
      </p>
      <p className="comparison-note">
        Search selects up to three runbooks from this library and up to three
        attachments separately. Results show exactly which references reached
        both models.
      </p>
      <button
        type="button"
        className="secondary-button"
        disabled={busy || disabled}
        onClick={() => {
          setError(null);
          refresh().catch((e) => setError(e.message));
        }}
      >
        Refresh library
      </button>
      {runbooks?.length === 0 && <p>No runbooks stored yet.</p>}
      {runbooks && (
        <ul className="runbook-list">
          {runbooks.map((r) => (
            <li key={r.id}>
              <details className="reference-detail">
                <summary>
                  {r.title} · {r.service} ·{" "}
                  {r.ready ? "Searchable" : "Awaiting embedding"}
                </summary>
                <code>{r.id}</code>
                <p className="reference-content">{r.content}</p>
              </details>
            </li>
          ))}
        </ul>
      )}
      <details>
        <summary>Add an official runbook</summary>
        <form
          className="runtime-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            setMessage("");
            try {
              const response = await fetch("/api/runbooks", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  Authorization: `Bearer ${adminToken.trim()}`,
                },
                body: JSON.stringify({ title, service, content }),
              });
              if (!response.ok)
                throw new Error(
                  response.status === 401
                    ? "Runbook admin token is missing or incorrect."
                    : response.status === 422
                      ? "Use a title, service and 1–6,000 characters of text."
                      : response.status === 503
                        ? "Runbook uploads are unavailable. Check the API configuration or retry later."
                        : "Runbook could not be stored. Refresh the library before retrying.",
                );
              const created: Runbook = await response.json();
              setRunbooks((current) =>
                current
                  ? [...current, created].sort((a, b) =>
                      a.title.localeCompare(b.title),
                    )
                  : null,
              );
              setTitle("");
              setService("");
              setContent("");
              setAdminToken("");
              fileVersion.current++;
              setMessage(
                `Added ${created.title}. It is now searchable for future assessments.`,
              );
              onChange();
              await refresh();
            } catch (e) {
              setError(
                e instanceof Error ? e.message : "Runbook could not be stored.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <fieldset className="runtime-fieldset" disabled={disabled || busy}>
            <legend>Publish to the shared library</legend>
            <p className="comparison-note">
              Upload UTF-8 Markdown or plain text, or paste below. Adding it
              designates it as official guidance for this workspace. Maximum
              6,000 characters. The included example runbooks are synthetic.
            </p>
            <label>
              Runbook admin token
              <input
                type="password"
                autoComplete="off"
                required
                value={adminToken}
                onChange={(e) => setAdminToken(e.target.value)}
              />
            </label>
            <label>
              Runbook file
              <input
                type="file"
                accept=".md,.markdown,.txt,text/plain,text/markdown"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  const version = ++fileVersion.current;
                  e.target.value = "";
                  if (!file) return;
                  setError(null);
                  if (
                    !/\.(md|markdown|txt)$/i.test(file.name) ||
                    file.size > 24000
                  ) {
                    setError(
                      "Choose a Markdown or text file of at most 24 KB and 6,000 characters.",
                    );
                    return;
                  }
                  try {
                    const text = new TextDecoder("utf-8", {
                      fatal: true,
                    }).decode(await file.arrayBuffer());
                    if (version !== fileVersion.current) return;
                    if (
                      !text.trim() ||
                      text.length > 6000 ||
                      text.includes("\u0000")
                    )
                      throw new Error();
                    setContent(text);
                    setTitle(
                      file.name
                        .replace(/\.(md|markdown|txt)$/i, "")
                        .slice(0, 200),
                    );
                  } catch {
                    setError("Use a UTF-8 text file with 1–6,000 characters.");
                  }
                }}
              />
            </label>
            <label>
              Title
              <input
                required
                maxLength={200}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              Service
              <input
                required
                maxLength={100}
                value={service}
                onChange={(e) => setService(e.target.value)}
              />
            </label>
            <label>
              Procedure
              <textarea
                required
                rows={7}
                maxLength={6000}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
            </label>
            <button
              type="submit"
              className="primary-button"
              disabled={
                !adminToken.trim() ||
                !title.trim() ||
                !service.trim() ||
                !content.trim()
              }
            >
              {busy ? "Adding runbook…" : "Add official runbook"}
            </button>
          </fieldset>
        </form>
      </details>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
