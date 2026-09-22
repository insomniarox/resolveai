import { afterEach, describe, expect, it, vi } from "vitest";
import { parseComparisonEvent, streamComparison } from "./comparison-api";
import { cloneExampleRuntimeBundle } from "./runtime-bundle";

const input = {
  bundle: cloneExampleRuntimeBundle(),
  candidates: ["An upstream endpoint is unavailable."],
};
const prepared = {
  type: "prepared",
  prepared: {
    comparison_id: "id",
    input_sha256: "hash",
    started_at: "2026-09-21T09:00:00Z",
    preparation_ms: 1,
    candidates: input.candidates,
    evidence: input.bundle.evidence,
    runbooks: [],
    documents: [],
  },
};
const branch = (provider: string) => ({
  type: "branch",
  branch: {
    provider,
    model: "model",
    outcome: "inconclusive",
    supporting_evidence_ids: [],
    evidence_relations: {},
    started_at: "2026-09-21T09:00:00Z",
    start_offset_ms: 1,
    duration_ms: 2,
    calls: [],
    attempted_calls: 1,
  },
});
const finished = {
  type: "finished",
  finished: { duration_ms: 3, cleanup: "not_needed" },
};
function mockStream(events: unknown[], split = false) {
  const bytes = new TextEncoder().encode(
    events.map((e) => JSON.stringify(e)).join("\n") + "\n",
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            if (split) {
              for (let i = 0; i < bytes.length; i += 13)
                controller.enqueue(bytes.slice(i, i + 13));
            } else controller.enqueue(bytes);
            controller.close();
          },
        }),
      ),
    ),
  );
}
afterEach(() => vi.unstubAllGlobals());
describe("comparison stream", () => {
  it("accepts chunked lines and independently completed branches", async () => {
    mockStream([prepared, branch("jev"), branch("openrouter"), finished], true);
    const events: unknown[] = [];
    await streamComparison(input, (e) => events.push(e));
    expect(events).toHaveLength(4);
  });
  it("retains a completed branch but rejects a truncated stream", async () => {
    mockStream([prepared, branch("jev")]);
    const events: unknown[] = [];
    await expect(
      streamComparison(input, (e) => events.push(e)),
    ).rejects.toThrow("before the comparison finished");
    expect(events).toHaveLength(2);
  });
  it("rejects citations not in shared evidence", async () => {
    const invalid = branch("jev");
    invalid.branch.outcome = "supported";
    Object.assign(invalid.branch, {
      candidate_index: 0,
      supporting_evidence_ids: ["invented"],
    });
    mockStream([prepared, invalid, branch("openrouter"), finished]);
    await expect(streamComparison(input, () => undefined)).rejects.toThrow(
      "Unknown comparison citation",
    );
  });
  it("rejects non-finite timings and invalid failure states", () => {
    expect(() =>
      parseComparisonEvent({
        ...finished,
        finished: { duration_ms: NaN, cleanup: "completed" },
      }),
    ).toThrow();
    const invalid = branch("jev");
    invalid.branch.outcome = "failed";
    expect(() => parseComparisonEvent(invalid)).toThrow();
  });
  it("allows shared preparation errors to finish without provider events", async () => {
    mockStream([{ type: "error", error: "input_too_large" }, finished]);
    await expect(
      streamComparison(input, () => undefined),
    ).resolves.toBeUndefined();
  });
});
