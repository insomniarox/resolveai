import { useState } from "react";

import type { KnowledgeDocument } from "@/lib/types";
import {
  MAX_RUNTIME_DOCUMENT_CHARACTERS,
  MAX_RUNTIME_DOCUMENTS,
  MAX_RUNTIME_DOCUMENT_TOTAL_CHARACTERS,
  RUNTIME_IDENTIFIER_PATTERN,
  createRuntimeDocument,
  runtimeDocumentsFromFiles,
} from "@/lib/runtime-bundle";

interface RuntimeKnowledgeDocumentEditorProps {
  disabled: boolean;
  documents: KnowledgeDocument[];
  onChange: (documents: KnowledgeDocument[]) => void;
  reservedIds: string[];
}

export function RuntimeKnowledgeDocumentEditor({
  disabled,
  documents,
  onChange,
  reservedIds,
}: RuntimeKnowledgeDocumentEditorProps) {
  const [fileError, setFileError] = useState<string | null>(null);
  const totalCharacters = documents.reduce(
    (total, document) => total + document.content.length,
    0,
  );

  function updateDocument(index: number, document: KnowledgeDocument) {
    setFileError(null);
    onChange(
      documents.map((current, position) =>
        position === index ? document : current,
      ),
    );
  }

  async function attachFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setFileError(null);
    try {
      const attached = await runtimeDocumentsFromFiles(
        Array.from(fileList),
        documents,
        reservedIds,
      );
      onChange([...documents, ...attached]);
    } catch (error) {
      setFileError(
        error instanceof Error ? error.message : "The selected files could not be read.",
      );
    }
  }

  return (
    <fieldset className="runtime-fieldset" disabled={disabled}>
      <legend>Reference documents</legend>
      <div className="runtime-fieldset-heading">
        <p className="runtime-section-help">
          Add short operational notes for request-scoped semantic retrieval.
        </p>
        <span className="count-summary">{documents.length} / 5</span>
      </div>

      <div className="runtime-document-actions">
        <button
          className="secondary-button"
          disabled={disabled || documents.length >= MAX_RUNTIME_DOCUMENTS}
          onClick={() =>
            onChange([...documents, createRuntimeDocument(reservedIds)])
          }
          type="button"
        >
          Add text document
        </button>
        <label className="runtime-file-button">
          Attach .txt or .md
          <input
            accept=".txt,.md,text/plain,text/markdown"
            disabled={disabled || documents.length >= MAX_RUNTIME_DOCUMENTS}
            multiple
            onChange={(event) => {
              void attachFiles(event.target.files);
              event.target.value = "";
            }}
            type="file"
          />
        </label>
      </div>

      <p className="runtime-character-total">
        {totalCharacters.toLocaleString()} /{" "}
        {MAX_RUNTIME_DOCUMENT_TOTAL_CHARACTERS.toLocaleString()} characters across
        all documents
      </p>
      {fileError && (
        <p className="runtime-inline-error" role="alert">
          {fileError}
        </p>
      )}

      {documents.length === 0 ? (
        <p className="runtime-empty-note">No reference documents attached.</p>
      ) : (
        <div className="runtime-card-list">
          {documents.map((document, index) => {
            const itemNumber = index + 1;
            return (
              <article className="runtime-editor-card" key={index}>
                <div className="runtime-card-heading">
                  <h3>Document {itemNumber}</h3>
                  <button
                    aria-label={`Remove document ${itemNumber}`}
                    className="runtime-remove-button"
                    onClick={() =>
                      onChange(
                        documents.filter((_, position) => position !== index),
                      )
                    }
                    type="button"
                  >
                    Remove
                  </button>
                </div>
                <div className="runtime-field-grid">
                  <label>
                    Document ID
                    <input
                      maxLength={128}
                      onChange={(event) =>
                        updateDocument(index, {
                          ...document,
                          id: event.target.value,
                        })
                      }
                      pattern={RUNTIME_IDENTIFIER_PATTERN}
                      required
                      value={document.id}
                    />
                  </label>
                  <label>
                    Content type
                    <select
                      onChange={(event) =>
                        updateDocument(index, {
                          ...document,
                          content_type: event.target.value as
                            | "text/plain"
                            | "text/markdown",
                        })
                      }
                      value={document.content_type}
                    >
                      <option value="text/plain">Plain text</option>
                      <option value="text/markdown">Markdown</option>
                    </select>
                  </label>
                  <label className="runtime-field-wide">
                    Title
                    <input
                      maxLength={160}
                      onChange={(event) =>
                        updateDocument(index, {
                          ...document,
                          title: event.target.value,
                        })
                      }
                      required
                      value={document.title}
                    />
                  </label>
                  <label className="runtime-field-wide">
                    Content
                    <textarea
                      className="runtime-document-content"
                      maxLength={MAX_RUNTIME_DOCUMENT_CHARACTERS}
                      onChange={(event) =>
                        updateDocument(index, {
                          ...document,
                          content: event.target.value,
                        })
                      }
                      required
                      rows={7}
                      value={document.content}
                    />
                  </label>
                </div>
                <p className="runtime-character-count">
                  {document.content.length.toLocaleString()} /{" "}
                  {MAX_RUNTIME_DOCUMENT_CHARACTERS.toLocaleString()} characters
                </p>
              </article>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
