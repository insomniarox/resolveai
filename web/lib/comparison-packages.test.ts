import { describe, expect, it } from "vitest";
import {
  cloneComparisonPackage,
  comparisonPackages,
} from "./comparison-packages";
import { validateRuntimeBundle } from "./runtime-bundle";

describe("comparison incident packages", () => {
  it("provides ten distinct complete requests accepted by the bundle editor", () => {
    expect(comparisonPackages).toHaveLength(10);
    expect(new Set(comparisonPackages.map((p) => p.id)).size).toBe(10);
    for (const { request } of comparisonPackages) {
      expect(validateRuntimeBundle(request.bundle)).toEqual([]);
      expect(request.bundle.evidence.length).toBeGreaterThanOrEqual(7);
      expect(request.bundle.knowledge_documents?.length).toBeGreaterThanOrEqual(
        2,
      );
      expect(request.candidates.length).toBeGreaterThanOrEqual(2);
      expect(request.candidates.length).toBeLessThanOrEqual(5);
      expect(new Set(request.candidates.map((c) => c.toLowerCase())).size).toBe(
        request.candidates.length,
      );
    }
  });

  it("isolates edits to observations, references and candidates from subsequent loads", () => {
    const id = comparisonPackages[0].id;
    const first = cloneComparisonPackage(id);
    first.bundle.evidence[0].details.changed = "edited";
    first.bundle.knowledge_documents![0].content = "edited";
    first.candidates[0] = "edited";
    expect(cloneComparisonPackage(id)).toEqual(comparisonPackages[0].request);
  });
});
