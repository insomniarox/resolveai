import type { Incident } from "@/lib/types";
import {
  RUNTIME_IDENTIFIER_PATTERN,
  toDateTimeLocalValue,
} from "@/lib/runtime-bundle";

interface RuntimeIncidentFieldsProps {
  disabled: boolean;
  incident: Incident;
  onChange: (incident: Incident) => void;
}

export function RuntimeIncidentFields({
  disabled,
  incident,
  onChange,
}: RuntimeIncidentFieldsProps) {
  function update(field: keyof Incident, value: string) {
    onChange({ ...incident, [field]: value });
  }

  return (
    <fieldset className="runtime-fieldset" disabled={disabled}>
      <legend>Incident</legend>
      <p className="runtime-section-help">
        Describe the affected service and when the incident began.
      </p>
      <div className="runtime-field-grid">
        <label>
          Incident ID
          <input
            maxLength={128}
            onChange={(event) => update("id", event.target.value)}
            pattern={RUNTIME_IDENTIFIER_PATTERN}
            required
            value={incident.id}
          />
        </label>
        <label>
          Service
          <input
            maxLength={100}
            onChange={(event) => update("service", event.target.value)}
            required
            value={incident.service}
          />
        </label>
        <label className="runtime-field-wide">
          Title
          <input
            maxLength={160}
            onChange={(event) => update("title", event.target.value)}
            required
            value={incident.title}
          />
        </label>
        <label className="runtime-field-wide">
          Description
          <textarea
            className="runtime-textarea-short"
            maxLength={2_000}
            onChange={(event) => update("description", event.target.value)}
            required
            rows={3}
            value={incident.description}
          />
        </label>
        <label>
          Started at
          <input
            onChange={(event) => update("started_at", event.target.value)}
            required
            type="datetime-local"
            value={toDateTimeLocalValue(incident.started_at)}
          />
        </label>
      </div>
    </fieldset>
  );
}
