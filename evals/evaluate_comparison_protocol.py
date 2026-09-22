"""Regression evaluation of the production two-stage comparison protocol.

Reuses pressure families already observed, so results are regression measurements,
not new held-out evidence. No application database or runtime data is accessed.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from evals.evaluate_jev_pressure import CASES_SHA256, load_cases
from resolve_ai.comparison import execute_branch
from resolve_ai.comparison_reasoner import COMPARISON_PROTOCOL, MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = load_cases()
    if args.live and args.max_calls < len(cases) * 4:
        parser.error("Reserve up to 40 calls for ten two-stage paired cases")
    if args.output.exists():
        parser.error("Choose a new output path")
    load_dotenv()
    if args.live and any(
        not os.environ.get(k, "").strip()
        for k in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY")
    ):
        parser.error("Both provider keys required")
    with args.output.open("x") as out:
        out.write(
            json.dumps(
                {
                    "manifest": {
                        "protocol": COMPARISON_PROTOCOL,
                        "dataset_sha256": CASES_SHA256,
                        "models": MODELS,
                        "started_at": datetime.now(UTC).isoformat(),
                        "live": args.live,
                        "max_calls": args.max_calls,
                    }
                }
            )
            + "\n"
        )
        out.flush()
        if args.live:
            with ThreadPoolExecutor(max_workers=2) as pool:
                for case in cases:
                    candidates = list(case["candidates"].values())
                    expected = (
                        None
                        if case["expected_cause"] == "none"
                        else list(case["candidates"]).index(case["expected_cause"])
                    )
                    start = perf_counter()
                    futures = [
                        pool.submit(execute_branch, p, case["state"], candidates, start)
                        for p in ("jev", "openrouter")
                    ]
                    for future in futures:
                        branch = future.result()
                        record = {
                            "case_id": case["id"],
                            "state": case["state"],
                            "candidates": candidates,
                            "expected_candidate_index": expected,
                            "correct": branch.outcome != "failed"
                            and branch.candidate_index == expected,
                            "branch": branch.model_dump(mode="json"),
                        }
                        out.write(json.dumps(record) + "\n")
                        out.flush()
                        print(
                            f"{branch.provider} {case['id']}: {branch.outcome}, correct={record['correct']}",
                            flush=True,
                        )


if __name__ == "__main__":
    main()
