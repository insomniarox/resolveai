"use client";

import { useState } from "react";

import { RuntimeEvidenceEditor } from "@/components/runtime-evidence-editor";
import { RuntimeIncidentFields } from "@/components/runtime-incident-fields";
import { RuntimeKnowledgeDocumentEditor } from "@/components/runtime-knowledge-document-editor";
import type { RuntimeIncidentBundle } from "@/lib/types";
import { parseRuntimeBundleJson } from "@/lib/runtime-bundle";

type EditorMode = "form" | "json";

interface RuntimeBundleEditorProps {
  bundle: RuntimeIncidentBundle;
  disabled: boolean;
  errors: string[];
  onChange: (bundle: RuntimeIncidentBundle) => void;
}

export function RuntimeBundleEditor({
  bundle,
  disabled,
  errors,
  onChange,
}: RuntimeBundleEditorProps) {
  const [mode, setMode] = useState<EditorMode>("form");
  const [jsonDraft, setJsonDraft] = useState(() => ({
    bundle,
    text: JSON.stringify(bundle, null, 2),
  }));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const jsonText =
    jsonDraft.bundle === bundle
      ? jsonDraft.text
      : JSON.stringify(bundle, null, 2);

  function selectMode(nextMode: EditorMode) {
    if (nextMode === "json") {
      setJsonDraft({ bundle, text: JSON.stringify(bundle, null, 2) });
    }
    setJsonError(null);
    setMode(nextMode);
  }

  function applyJson() {
    try {
      onChange(parseRuntimeBundleJson(jsonText));
      setJsonError(null);
    } catch (error) {
      setJsonError(
        error instanceof SyntaxError
          ? "The bundle is not valid JSON. Check commas, quotes, and brackets."
          : error instanceof Error
            ? error.message
            : "The JSON bundle could not be applied.",
      );
    }
  }

  const documents = bundle.knowledge_documents ?? [];
  const reservedIds = [
    ...bundle.evidence.map((item) => item.id),
    ...documents.map((item) => item.id),
  ];

  return (
    <div className="runtime-bundle-editor">
      <div aria-label="Runtime bundle editor" className="runtime-editor-tabs" role="tablist">
        <button
          aria-controls="runtime-form-editor"
          aria-selected={mode === "form"}
          className="runtime-editor-tab"
          onClick={() => selectMode("form")}
          role="tab"
          type="button"
        >
          Form
        </button>
        <button
          aria-controls="runtime-json-editor-panel"
          aria-selected={mode === "json"}
          className="runtime-editor-tab"
          onClick={() => selectMode("json")}
          role="tab"
          type="button"
        >
          JSON
        </button>
      </div>

      {errors.length > 0 && (
        <div className="runtime-validation-summary" role="alert">
          <strong>Fix the runtime input before investigating.</strong>
          <ul>
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      {mode === "form" ? (
        <div aria-label="Runtime bundle form" id="runtime-form-editor" role="tabpanel">
          <RuntimeIncidentFields
            disabled={disabled}
            incident={bundle.incident}
            onChange={(incident) => onChange({ ...bundle, incident })}
          />
          <RuntimeEvidenceEditor
            disabled={disabled}
            evidence={bundle.evidence}
            onChange={(evidence) => onChange({ ...bundle, evidence })}
          />
          <RuntimeKnowledgeDocumentEditor
            disabled={disabled}
            documents={documents}
            onChange={(knowledge_documents) =>
              onChange({ ...bundle, knowledge_documents })
            }
            reservedIds={reservedIds}
          />
        </div>
      ) : (
        <div
          aria-label="Runtime bundle JSON"
          className="runtime-json-panel"
          id="runtime-json-editor-panel"
          role="tabpanel"
        >
          <label htmlFor="runtime-bundle-json">Incident bundle JSON</label>
          <textarea
            className="runtime-json-editor"
            disabled={disabled}
            id="runtime-bundle-json"
            onChange={(event) => {
              setJsonDraft({ bundle, text: event.target.value });
              setJsonError(null);
            }}
            spellCheck={false}
            value={jsonText}
          />
          <p className="runtime-section-help">
            Apply JSON before investigating. Invalid text stays here and does not change the form.
          </p>
          {jsonError && (
            <p className="runtime-inline-error" role="alert">
              {jsonError}
            </p>
          )}
          <button
            className="secondary-button"
            disabled={disabled}
            onClick={applyJson}
            type="button"
          >
            Apply JSON
          </button>
        </div>
      )}
    </div>
  );
}
