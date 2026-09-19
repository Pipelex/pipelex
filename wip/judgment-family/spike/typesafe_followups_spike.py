"""Second half of the TypeSafe spike: the questions the first run raised.

    uv run --no-project --with typesafe-sdk --with httpx --env-file .env \
        python wip/judgment-family/spike/typesafe_followups_spike.py

The first run showed that `/v1/models` lists only the two aliases while a
response reports `jev-1.13.0`, and that an unambiguous case is bit-identical
across repeats. This run asks whether a versioned id can be requested at all,
how a genuinely ambiguous case moves, what an unknown criteria key does, and
what the rate limit looks like.
"""

# ruff: file-ignore[implicit-namespace-package]

from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, Score, TypeSafeError

RESPONSES_DIR = Path(__file__).parent / "responses"
findings: list[tuple[str, str]] = []


def record(label: str, value: Any) -> None:
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    findings.append((label, text))
    print(f"  {label}: {text}")


def save(name: str, payload: Any) -> None:
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    (RESPONSES_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


def describe_exception(exc: BaseException) -> dict[str, Any]:
    detail: dict[str, Any] = {"class": type(exc).__name__, "str": str(exc)[:400]}
    for attribute in ("status", "request_id"):
        if hasattr(exc, attribute):
            detail[attribute] = getattr(exc, attribute)
    if getattr(exc, "body", None) is not None:
        detail["body"] = exc.body  # type: ignore[attr-defined]
    return detail


def heading(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# A deliberately borderline message: neither clearly urgent nor clearly not.
AMBIGUOUS = (
    "Hi -- the export button on the reports page sometimes takes a while and once it did nothing at all. "
    "It worked when I tried again. Not sure if this is worth reporting, but thought you should know."
)


async def probe_versioned_model(client: AsyncTypeSafeClient) -> None:
    heading("A. Can a versioned id be requested?")
    for candidate in ("jev-1.13.0", "jev-1.13", "jev-1", "jev"):
        try:
            response = await client.system_one(
                state={"message": AMBIGUOUS}, questions={"q": Noul(instructions="Is the message urgent?")}, model=candidate
            )
        except TypeSafeError as exc:
            record(f"model {candidate!r}", describe_exception(exc))
            continue
        record(f"model {candidate!r} accepted", {"reported": response.model})

    default = await client.system_one(state={"message": AMBIGUOUS}, questions={"q": Noul(instructions="Is the message urgent?")})
    record("no model named (SDK default)", {"reported": default.model})


async def probe_ambiguous_stability(client: AsyncTypeSafeClient, repeats: int = 10) -> None:
    heading("B. Stability on a genuinely ambiguous case")
    questions = {
        "is_urgent": Noul(instructions="Is the message urgent?"),
        "team": Choice(
            instructions="Which team should handle this message?",
            criteria={"reports": "Reporting and exports", "performance": "Slowness and timeouts", "other": "None of the above"},
        ),
        "severity": Score(
            instructions="How severe is the reported issue?",
            criteria=[
                "Cosmetic; no impact on functionality",
                "A feature is degraded, but a workaround exists",
                "Blocking issue; no workaround exists",
            ],
        ),
    }
    state = {"message": AMBIGUOUS}
    responses = await asyncio.gather(*(client.system_one(state=state, questions=questions) for _ in range(repeats)))
    save("B_ambiguous_stability", [r.model_dump(mode="json") for r in responses])

    nouls = [r.nouls["is_urgent"].noul for r in responses]
    choices = [r.choices["team"].choice for r in responses]
    confidences = [r.choices["team"].confidence for r in responses]
    scores = [r.scores["severity"].score for r in responses]

    record("ambiguous noul values", sorted({round(v, 4) for v in nouls}))
    record("ambiguous noul spread", round(max(nouls) - min(nouls), 4))
    record("ambiguous noul stdev", round(statistics.pstdev(nouls), 4))
    record("ambiguous choice verdicts", sorted(set(choices)))
    record("ambiguous choice verdict stable", len(set(choices)) == 1)
    record("ambiguous choice confidence range", [round(min(confidences), 4), round(max(confidences), 4)])
    record("ambiguous score values", sorted({round(v, 4) for v in scores}))
    record("ambiguous score spread", round(max(scores) - min(scores), 4))
    record("ambiguous responses bit-identical", len({json.dumps(r.model_dump(mode="json")["answers"], sort_keys=True) for r in responses}) == 1)

    # The same question under a reworded instruction, to see how far wording moves it.
    reworded = await client.system_one(state=state, questions={"q": Noul(instructions="Does this message need attention today?")})
    record("reworded instruction, noul", round(reworded.nouls["q"].noul, 4))


async def probe_criteria_keys(client: AsyncTypeSafeClient) -> None:
    heading("C. Noul criteria keys")
    cases: dict[str, Any] = {
        "true_and_false": Noul(instructions="Is the message urgent?", criteria={"true": "Needs attention now", "false": "Can wait"}),
        "false_only": Noul(instructions="Is the message urgent?", criteria={"false": "Can wait"}),
        "unknown_key": {"type": "noul", "instructions": "Is the message urgent?", "criteria": {"maybe": "who knows"}},
        "criteria_only_no_instructions": {"type": "noul", "criteria": {"true": "Needs attention now", "false": "Can wait"}},
        "empty_criteria": Noul(instructions="Is the message urgent?", criteria={}),
        "empty_instructions": {"type": "noul", "instructions": ""},
        "structured_instructions": Noul(
            instructions={"task": "Decide urgency", "rule": "Treat a total outage as urgent"},
        ),
    }
    for name, question in cases.items():
        try:
            response = await client.system_one(state={"message": AMBIGUOUS}, questions={"q": question})  # type: ignore[dict-item]
        except TypeSafeError as exc:
            record(name, describe_exception(exc))
            continue
        record(name, response.model_dump(mode="json")["answers"]["q"])

    heading("C2. Choice option keys")
    for name, criteria in (
        ("keys_with_spaces", {"needs triage": None, "no action": None}),
        ("keys_with_dots", {"team.reports": None, "team.performance": None}),
        ("unicode_keys", {"rapport": None, "réseau": None}),
        ("empty_string_key", {"": "no description", "other": None}),
        ("duplicate_after_strip", {"a": None, "A": None}),
        ("empty_string_description", {"reports": "", "other": ""}),
    ):
        try:
            response = await client.system_one(
                state={"message": AMBIGUOUS},
                questions={"q": Choice(instructions="Which team should handle this message?", criteria=criteria)},
            )
        except TypeSafeError as exc:
            record(name, describe_exception(exc))
            continue
        record(name, response.model_dump(mode="json")["answers"]["q"])


async def probe_question_count(client: AsyncTypeSafeClient) -> None:
    heading("D. How many questions fit in one request")
    state = {"message": AMBIGUOUS}
    for count in (1, 5, 20, 50):
        questions = {f"q{i:02d}": Noul(instructions=f"Is the message about topic number {i}?") for i in range(count)}
        started = time.perf_counter()
        try:
            response = await client.system_one(state=state, questions=questions)
        except TypeSafeError as exc:
            record(f"{count} questions", describe_exception(exc))
            continue
        record(
            f"{count} questions",
            {
                "latency_s": round(time.perf_counter() - started, 3),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "answers": len(response.answers),
            },
        )


async def probe_rate_limit(client: AsyncTypeSafeClient, burst: int = 40) -> None:
    heading("E. Rate limit under a burst")
    state = {"message": AMBIGUOUS}
    started = time.perf_counter()
    results = await asyncio.gather(
        *(client.system_one(state=state, questions={"q": Noul(instructions="Is the message urgent?")}) for _ in range(burst)),
        return_exceptions=True,
    )
    failures = [describe_exception(r) for r in results if isinstance(r, BaseException)]
    record(f"{burst} concurrent requests, elapsed_s", round(time.perf_counter() - started, 3))
    record("failures", failures or "none")
    if failures:
        save("E_rate_limit_failures", failures)


async def main() -> None:
    async with AsyncTypeSafeClient(retry=RetryPolicy(max_retries=0), timeout=60.0) as client:
        await probe_versioned_model(client)
        await probe_ambiguous_stability(client)
        await probe_criteria_keys(client)
        await probe_question_count(client)
        await probe_rate_limit(client)

    heading("Summary")
    save("99_followup_findings", [{"label": label, "value": value} for label, value in findings])
    print(f"{len(findings)} findings")


if __name__ == "__main__":
    asyncio.run(main())
