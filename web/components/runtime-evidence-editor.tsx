import {
  EVIDENCE_KINDS,
  EVIDENCE_SOURCES,
  type Evidence,
  type EvidenceKind,
  type EvidenceSource,
} from "@/lib/types";
import {
  MAX_RUNTIME_DETAILS,
  MAX_RUNTIME_EVIDENCE,
  RUNTIME_DETAIL_KEY_PATTERN,
  RUNTIME_IDENTIFIER_PATTERN,
  createRuntimeEvidence,
  readableOption,
  toDateTimeLocalValue,
} from "@/lib/runtime-bundle";

interface RuntimeEvidenceEditorProps {
  disabled: boolean;
  evidence: Evidence[];
  onChange: (evidence: Evidence[]) => void;
}

function nextDetailKey(details: Evidence["details"]): string {
  let index = Object.keys(details).length + 1;
  while (`detail_${index}` in details) index += 1;
  return `detail_${index}`;
}

function replaceDetailKey(
  details: Evidence["details"],
  oldKey: string,
  newKey: string,
): Evidence["details"] {
  if (newKey !== oldKey && newKey in details) return details;
  return Object.fromEntries(
    Object.entries(details).map(([key, value]) =>
      key === oldKey ? [newKey, value] : [key, value],
    ),
  );
}

export function RuntimeEvidenceEditor({
  disabled,
  evidence,
  onChange,
}: RuntimeEvidenceEditorProps) {
  function updateEvidence(index: number, item: Evidence) {
    onChange(evidence.map((current, position) => (position === index ? item : current)));
  }

  function removeEvidence(index: number) {
    if (evidence.length <= 1) return;
    onChange(evidence.filter((_, position) => position !== index));
  }

  return (
    <fieldset className="runtime-fieldset" disabled={disabled}>
      <legend>Observed evidence</legend>
      <div className="runtime-fieldset-heading">
        <p className="runtime-section-help">
          Add normalized facts that the diagnosis may cite.
        </p>
        <span className="count-summary">{evidence.length} / 50</span>
      </div>

      <div className="runtime-card-list">
        {evidence.map((item, index) => {
          const details = Object.entries(item.details);
          const itemNumber = index + 1;
          return (
            <article className="runtime-editor-card" key={index}>
              <div className="runtime-card-heading">
                <h3>Evidence {itemNumber}</h3>
                <button
                  aria-label={`Remove evidence ${itemNumber}`}
                  className="runtime-remove-button"
                  disabled={disabled || evidence.length <= 1}
                  onClick={() => removeEvidence(index)}
                  type="button"
                >
                  Remove
                </button>
              </div>

              <div className="runtime-field-grid">
                <label>
                  Evidence ID
                  <input
                    maxLength={128}
                    onChange={(event) =>
                      updateEvidence(index, { ...item, id: event.target.value })
                    }
                    pattern={RUNTIME_IDENTIFIER_PATTERN}
                    required
                    value={item.id}
                  />
                </label>
                <label>
                  Observed at
                  <input
                    onChange={(event) =>
                      updateEvidence(index, {
                        ...item,
                        observed_at: event.target.value,
                      })
                    }
                    required
                    type="datetime-local"
                    value={toDateTimeLocalValue(item.observed_at)}
                  />
                </label>
                <label>
                  Source
                  <select
                    onChange={(event) =>
                      updateEvidence(index, {
                        ...item,
                        source: event.target.value as EvidenceSource,
                      })
                    }
                    value={item.source}
                  >
                    {EVIDENCE_SOURCES.map((source) => (
                      <option key={source} value={source}>
                        {readableOption(source)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Kind
                  <select
                    onChange={(event) =>
                      updateEvidence(index, {
                        ...item,
                        kind: event.target.value as EvidenceKind,
                      })
                    }
                    value={item.kind}
                  >
                    {EVIDENCE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {readableOption(kind)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="runtime-field-wide">
                  Summary
                  <textarea
                    className="runtime-textarea-short"
                    maxLength={2_000}
                    onChange={(event) =>
                      updateEvidence(index, {
                        ...item,
                        summary: event.target.value,
                      })
                    }
                    required
                    rows={2}
                    value={item.summary}
                  />
                </label>
              </div>

              <div className="runtime-details-heading">
                <span>Structured details</span>
                <button
                  className="runtime-add-link"
                  disabled={disabled || details.length >= MAX_RUNTIME_DETAILS}
                  onClick={() =>
                    updateEvidence(index, {
                      ...item,
                      details: {
                        ...item.details,
                        [nextDetailKey(item.details)]: "value",
                      },
                    })
                  }
                  type="button"
                >
                  Add detail
                </button>
              </div>
              {details.length === 0 ? (
                <p className="runtime-empty-note">No structured details.</p>
              ) : (
                <div className="runtime-detail-list">
                  {details.map(([key, value], detailIndex) => (
                    <div className="runtime-detail-row" key={`${key}-${detailIndex}`}>
                      <label>
                        <span className="visually-hidden">
                          Evidence {itemNumber} detail key
                        </span>
                        <input
                          aria-label={`Evidence ${itemNumber} detail key`}
                          maxLength={64}
                          onChange={(event) =>
                            updateEvidence(index, {
                              ...item,
                              details: replaceDetailKey(
                                item.details,
                                key,
                                event.target.value,
                              ),
                            })
                          }
                          pattern={RUNTIME_DETAIL_KEY_PATTERN}
                          required
                          value={key}
                        />
                      </label>
                      <label>
                        <span className="visually-hidden">
                          Evidence {itemNumber} detail type
                        </span>
                        <select
                          aria-label={`Evidence ${itemNumber} detail type`}
                          onChange={(event) => {
                            const nextValue =
                              event.target.value === "integer"
                                ? typeof value === "number"
                                  ? value
                                  : /^-?\d+$/.test(value)
                                    ? Number(value)
                                    : 0
                                : String(value);
                            updateEvidence(index, {
                              ...item,
                              details: { ...item.details, [key]: nextValue },
                            });
                          }}
                          value={typeof value === "number" ? "integer" : "string"}
                        >
                          <option value="string">Text</option>
                          <option value="integer">Integer</option>
                        </select>
                      </label>
                      <label>
                        <span className="visually-hidden">
                          Evidence {itemNumber} detail value
                        </span>
                        <input
                          aria-label={`Evidence ${itemNumber} detail value`}
                          maxLength={typeof value === "string" ? 500 : undefined}
                          onChange={(event) =>
                            updateEvidence(index, {
                              ...item,
                              details: {
                                ...item.details,
                                [key]:
                                  typeof value === "number"
                                    ? Number(event.target.value)
                                    : event.target.value,
                              },
                            })
                          }
                          required
                          step={typeof value === "number" ? 1 : undefined}
                          type={typeof value === "number" ? "number" : "text"}
                          value={value}
                        />
                      </label>
                      <button
                        aria-label={`Remove detail ${key} from evidence ${itemNumber}`}
                        className="runtime-detail-remove"
                        onClick={() => {
                          const nextDetails = { ...item.details };
                          delete nextDetails[key];
                          updateEvidence(index, { ...item, details: nextDetails });
                        }}
                        type="button"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>

      <button
        className="secondary-button runtime-add-button"
        disabled={disabled || evidence.length >= MAX_RUNTIME_EVIDENCE}
        onClick={() => onChange([...evidence, createRuntimeEvidence(evidence)])}
        type="button"
      >
        Add evidence
      </button>
    </fieldset>
  );
}
