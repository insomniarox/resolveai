import type { Incident } from "@/lib/types";

interface IncidentListProps {
  incidents: Incident[];
  selectedIncidentId: string | null;
  disabled: boolean;
  onSelect: (incidentId: string) => void;
}

const dateTimeFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function IncidentList({
  incidents,
  selectedIncidentId,
  disabled,
  onSelect,
}: IncidentListProps) {
  return (
    <nav aria-label="Available incidents" className="incident-list">
      {incidents.map((incident) => {
        const selected = incident.id === selectedIncidentId;
        return (
          <button
            aria-pressed={selected}
            className="incident-list-item"
            disabled={disabled}
            key={incident.id}
            onClick={() => onSelect(incident.id)}
            type="button"
          >
            <span className="incident-list-heading">
              <span className="incident-id">{incident.id}</span>
              <span className="service-label">{incident.service}</span>
            </span>
            <strong>{incident.title}</strong>
            <time dateTime={incident.started_at}>
              {dateTimeFormatter.format(new Date(incident.started_at))} UTC
            </time>
          </button>
        );
      })}
    </nav>
  );
}
