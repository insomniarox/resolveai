import { describe, expect, it } from "vitest";

import {
  MAX_RUNTIME_DOCUMENT_CHARACTERS,
  RUNTIME_DETAIL_KEY_PATTERN,
  RUNTIME_IDENTIFIER_PATTERN,
  cloneExampleRuntimeBundle,
  parseRuntimeBundleJson,
  prepareRuntimeBundle,
  runtimeDocumentsFromFiles,
  validateRuntimeBundle,
} from "./runtime-bundle";

describe("runtime bundle helpers", () => {
  it("keeps native HTML patterns compatible with Unicode Sets mode", () => {
    expect(() => new RegExp(RUNTIME_IDENTIFIER_PATTERN, "v")).not.toThrow();
    expect(() => new RegExp(RUNTIME_DETAIL_KEY_PATTERN, "v")).not.toThrow();
  });

  it("clones the example so form edits do not mutate the shared fixture", () => {
    const first = cloneExampleRuntimeBundle();
    const second = cloneExampleRuntimeBundle();

    first.incident.id = "CHANGED";

    expect(second.incident.id).toBe("USER-INC-901");
  });

  it("normalizes form timestamps into offset timestamps", () => {
    const bundle = cloneExampleRuntimeBundle();
    bundle.incident.started_at = "2026-08-17T09:00";
    bundle.evidence[0].observed_at = "2026-08-17T09:01";

    const prepared = prepareRuntimeBundle(bundle);

    expect(prepared.incident.started_at).toMatch(/Z$/);
    expect(prepared.evidence[0].observed_at).toMatch(/Z$/);
    expect(validateRuntimeBundle(prepared)).toEqual([]);
  });

  it("reports duplicate IDs across evidence and documents", () => {
    const bundle = cloneExampleRuntimeBundle();
    bundle.knowledge_documents![0].id = bundle.evidence[0].id;

    expect(validateRuntimeBundle(bundle)).toContain(
      "Knowledge document IDs must differ from evidence IDs.",
    );
  });

  it("keeps integer and string detail values when applying JSON", () => {
    const bundle = cloneExampleRuntimeBundle();
    const parsed = parseRuntimeBundleJson(JSON.stringify(bundle));

    expect(parsed.evidence[0].details.status_code).toBe(503);
    expect(parsed.evidence[0].details.endpoint).toBe(
      "signing.partner.example/receipt",
    );
  });

  it("rejects unknown JSON fields before they reach the API", () => {
    const bundle = {
      ...cloneExampleRuntimeBundle(),
      unexpected: true,
    };

    expect(() => parseRuntimeBundleJson(JSON.stringify(bundle))).toThrow(
      "unknown field",
    );
  });

  it("turns text and Markdown files into bounded knowledge documents", async () => {
    const files = [
      new File(["Plain operational note"], "operations.txt", {
        type: "text/plain",
      }),
      new File(["# Runbook"], "runbook.md", { type: "text/markdown" }),
    ];

    const documents = await runtimeDocumentsFromFiles(files, [], ["DOC-001"]);

    expect(documents).toMatchObject([
      {
        id: "DOC-002",
        title: "operations",
        content_type: "text/plain",
      },
      {
        id: "DOC-003",
        title: "runbook",
        content_type: "text/markdown",
      },
    ]);
  });

  it("rejects attached files above the document character limit", async () => {
    const file = new File(
      ["x".repeat(MAX_RUNTIME_DOCUMENT_CHARACTERS + 1)],
      "large.txt",
      { type: "text/plain" },
    );

    await expect(runtimeDocumentsFromFiles([file], [], [])).rejects.toThrow(
      "more than 8,000 characters",
    );
  });
});
