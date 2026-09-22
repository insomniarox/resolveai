"""Frozen pressure cases with atomic evidence claims and candidate-order controls."""

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from evals.evaluate_jev_decisions import (
    JEV_MODEL,
    MAX_OUTPUT_TOKENS,
    POLICY,
    TIMEOUT,
    attempt,
    call_jev,
    call_openrouter,
    digest,
    summarize,
)
from resolve_ai.openrouter_model import OPENROUTER_REASONING_MODEL

CASES_PATH = Path(__file__).with_name("jev_pressure_cases.json")
CASES_SHA256 = "e7efa856cd650ff9a7ab1620690613259cf8f3fc4f1170955f4d28b15f19ae84"
PROTOCOL = "jev-atomic-pressure-v2"


def load_cases():
    content = CASES_PATH.read_bytes()
    if hashlib.sha256(content).hexdigest() != CASES_SHA256:
        raise ValueError("Frozen pressure dataset changed")
    return json.loads(content)["cases"]


def build_trial(case, reverse=False):
    candidates = list(case["candidates"].items())
    if reverse:
        candidates.reverse()
    questions = {
        "cause": {
            "type": "choice",
            "instructions": POLICY
            + " Which single listed cause is established for this incident? Choose none if no candidate fits, observations conflict without a resolution, or multiple causes remain possible.",
            "criteria": dict(
                candidates + [("none", "No single listed cause is established.")]
            ),
        }
    }
    expected = {"cause": case["expected_cause"]}
    for i, relation in enumerate(case["expected_relations"]):
        key = f"evidence_{i + 1}"
        questions[key] = {
            "type": "choice",
            "instructions": POLICY
            + f" Evaluate only observation E{i + 1} against this atomic claim: {case['claim']} Do not borrow facts from other observations. References may clarify terms but cannot establish an unobserved fact.",
            "criteria": {
                "supports": "The observation directly affirms this claim.",
                "contradicts": "The observation directly rules out this claim.",
                "insufficient": "The observation neither affirms nor rules out this claim.",
            },
        }
        expected[key] = relation
    request = {"state": deepcopy(case["state"]), "questions": questions}
    return {
        "case_id": case["id"],
        "split": case["split"],
        "variant": "reversed" if reverse else "original",
        "pressure": case["pressure"],
        "request": request,
        "request_sha256": digest(request),
        "expected": expected,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    trials = [
        build_trial(c, reverse) for c in load_cases() for reverse in (False, True)
    ]
    if args.live and len(trials) * 2 > args.max_calls:
        parser.error("Call budget is too small")
    if args.output.exists():
        parser.error("Choose a new output path")
    if args.live:
        load_dotenv()
        if any(
            not os.environ.get(k, "").strip()
            for k in ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY")
        ):
            parser.error("Both provider keys are required")
    manifest = {
        "protocol": PROTOCOL,
        "dataset_sha256": CASES_SHA256,
        "created_at": datetime.now(UTC).isoformat(),
        "live": args.live,
        "models": {"jev": JEV_MODEL, "openrouter": OPENROUTER_REASONING_MODEL},
        "timeout_seconds": TIMEOUT,
        "retry_count": 0,
        "openrouter_reasoning_effort": "medium",
        "openrouter_max_output_tokens": MAX_OUTPUT_TOKENS,
        "trials": trials,
    }
    records = []
    with args.output.open("x") as output:
        output.write(json.dumps({"manifest": manifest}) + "\n")
        output.flush()
        if args.live:
            with ThreadPoolExecutor(max_workers=2) as pool:
                for trial in trials:
                    futures = [
                        pool.submit(attempt, trial, p, c)
                        for p, c in [("jev", call_jev), ("openrouter", call_openrouter)]
                    ]
                    for future in futures:
                        record = future.result()
                        records.append(record)
                        output.write(json.dumps(record) + "\n")
                        output.flush()
                        print(
                            f"{record['provider']} {record['case_id']}/{record['variant']}: {record['outcome']} {record.get('correct')}",
                            flush=True,
                        )
        output.write(json.dumps({"summary": summarize(records)}) + "\n")
    print(json.dumps(summarize(records), indent=2))


if __name__ == "__main__":
    main()
