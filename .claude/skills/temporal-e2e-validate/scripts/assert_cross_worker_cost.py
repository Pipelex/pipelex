#!/usr/bin/env python3
"""Numeric cross-worker cost assertion for temporal-e2e-validate Tier 8b.

Turns the old "eyeball that a cost table rendered" check into a real assertion:
reads the NDJSON usage events a split-worker run produced, sums input/output
tokens straight from the events, and (optionally) cross-checks them against the
un-truncated CSV cost report and against expected per-call counts. The terminal
Rich table truncates wide columns to ``0 … …``, so this is the only reliable way
to confirm the real numbers cross the runner boundary and aggregate.

Pure stdlib (no pipelex import) so it runs fast and never perturbs the run.

Usage:
    .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py \
        --run-dir .pipelex/traces/<RUN_ID> \
        [--expected-events N] [--expected-input N] [--expected-output N] \
        [--expected-model-type llm|img_gen|extract|search] \
        [--reports-dir reports] [--require-fallback]

Exit code 0 = all assertions passed, 1 = at least one failed.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

_INPUT_KEYS = ("input",)
_OUTPUT_KEYS = ("output",)


def _load_usage_events(run_dir: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for ndjson_path in sorted(run_dir.glob("*.ndjson")):
        for line in ndjson_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("event_kind") == "usage_report":
                events.append(event)
    return events


def _sum_tokens(events: list[dict[str, Any]]) -> tuple[int, int]:
    total_input = 0
    total_output = 0
    for event in events:
        by_category = event.get("tokens_usage", {}).get("nb_tokens_by_category", {})
        total_input += sum(int(by_category.get(key, 0)) for key in _INPUT_KEYS)
        total_output += sum(int(by_category.get(key, 0)) for key in _OUTPUT_KEYS)
    return total_input, total_output


def _csv_token_totals(reports_dir: Path) -> tuple[int, int] | None:
    """Sum input-joined + output token columns across the most recent cost_report CSV, if any."""
    csv_paths = sorted(reports_dir.glob("cost_report*.csv"))
    if not csv_paths:
        return None
    latest = csv_paths[-1]
    total_input = 0
    total_output = 0
    with latest.open(encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            total_input += int(float(row.get("nb_tokens_input_joined") or 0))
            total_output += int(float(row.get("nb_tokens_output") or 0))
    return total_input, total_output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path, help="The .pipelex/traces/<RUN_ID> directory")
    parser.add_argument("--expected-events", type=int, default=None, help="Expected usage-event count (== number of inference calls)")
    parser.add_argument("--expected-input", type=int, default=None, help="Expected total input tokens")
    parser.add_argument("--expected-output", type=int, default=None, help="Expected total output tokens")
    parser.add_argument("--expected-model-type", default=None, help="Assert every usage record has this model_type")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"), help="Dir holding the un-truncated cost_report*.csv")
    parser.add_argument("--require-fallback", action="store_true", help="Require at least one act_* writer_id (runner fallback engaged)")
    parser.add_argument(
        "--require-nonzero", action="store_true", help="Require total input AND output tokens > 0 (real-spend arms, where exact counts are unknown)"
    )
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        print(f"FAIL: run dir not found: {run_dir}")
        return 1

    events = _load_usage_events(run_dir)
    failures: list[str] = []

    if not events:
        print(f"FAIL: no usage_report events under {run_dir}")
        return 1

    writer_ids = sorted({event.get("writer_id", "") for event in events})
    model_types = sorted({event.get("tokens_usage", {}).get("model_type", "?") for event in events})
    model_names = sorted({event.get("tokens_usage", {}).get("inference_model_name", "?") for event in events})
    total_input, total_output = _sum_tokens(events)

    print(f"usage events     : {len(events)}")
    print(f"writer_ids       : {writer_ids}")
    print(f"model_types      : {model_types}")
    print(f"model_names      : {model_names}")
    print(f"total tokens     : input={total_input} output={total_output} (joined+output={total_input + total_output})")

    csv_totals = _csv_token_totals(args.reports_dir)
    if csv_totals is not None:
        csv_input, csv_output = csv_totals
        print(f"csv tokens       : input={csv_input} output={csv_output}")
        if (csv_input, csv_output) != (total_input, total_output):
            failures.append(f"CSV totals {csv_totals} != NDJSON totals {(total_input, total_output)}")
    else:
        print(f"csv tokens       : (no cost_report*.csv under {args.reports_dir}; enable is_generate_cost_report_file_enabled to cross-check)")

    if args.require_fallback and not any(writer_id.startswith("act_") for writer_id in writer_ids):
        failures.append(f"no act_* writer_id (runner fallback did not engage); writer_ids={writer_ids}")
    if args.require_nonzero and not (total_input > 0 and total_output > 0):
        failures.append(f"expected non-zero input AND output tokens, got input={total_input} output={total_output}")
    if args.expected_events is not None and len(events) != args.expected_events:
        failures.append(f"event count {len(events)} != expected {args.expected_events}")
    if args.expected_input is not None and total_input != args.expected_input:
        failures.append(f"input tokens {total_input} != expected {args.expected_input}")
    if args.expected_output is not None and total_output != args.expected_output:
        failures.append(f"output tokens {total_output} != expected {args.expected_output}")
    if args.expected_model_type is not None and model_types != [args.expected_model_type]:
        failures.append(f"model_types {model_types} != [{args.expected_model_type!r}]")

    if failures:
        print("RESULT: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
