import catalog from "./data/comparison-packages.json";
import { parseRuntimeBundleJson } from "./runtime-bundle";
import type { RuntimeIncidentBundle } from "./types";

export interface ComparisonInput {
  bundle: RuntimeIncidentBundle;
  candidates: string[];
}

export const comparisonPackages = catalog.map((entry) => ({
  ...entry,
  request: {
    bundle: parseRuntimeBundleJson(JSON.stringify(entry.request.bundle)),
    candidates: entry.request.candidates,
  } satisfies ComparisonInput,
}));

export function cloneComparisonPackage(id: string): ComparisonInput {
  const entry = comparisonPackages.find((item) => item.id === id);
  if (!entry) throw new Error("Unknown incident package.");
  return structuredClone(entry.request);
}

export function downloadComparisonJson(value: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
