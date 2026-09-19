"""Throwaway spike against TypeSafe's System One API.

Run it from the worktree root:

    uv run --no-project --with typesafe-sdk --with httpx --env-file .env \
        python wip/judgment-family/spike/typesafe_async_spike.py

It answers the questions in `wip/judgment-family/plan.md`, phase 1: the answer
shapes, usage reporting, which state value types are accepted, criteria edge
cases, model pinning, error classification, retries, concurrency, stability, and
what the SDK buys over a plain POST. Every raw response body is written to
`responses/` (bodies only -- no key, no request headers) so that phase 2's unit
tests can replay them.

No `pipelex` import, no abstraction, no test. It is meant to be read once and
deleted.
"""

# ruff: file-ignore[implicit-namespace-package]

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import httpx
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    Noul,
    RetryPolicy,
    Score,
    SystemOneResponse,
    TypeSafeAPITimeoutError,
    TypeSafeError,
)

RESPONSES_DIR = Path(__file__).parent / "responses"
BASE_URL = "https://api.typesafe.ai"
NO_KEY = "TYPESAFE_API_KEY is not set; run with --env-file .env"

# The material every probe judges, so that answers stay comparable across probes.
MESSAGE = (
    "Our production checkout has been returning 500s for every card payment since 09:14 UTC. "
    "Nothing is going through. I have three customers on the phone right now. Please help."
)

findings: list[tuple[str, str]] = []


def record(label: str, value: Any) -> None:
    """Print a finding and keep it for the end-of-run summary."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, sort_keys=True)
    findings.append((label, text))
    print(f"  {label}: {text}")


def save(name: str, payload: Any) -> None:
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    (RESPONSES_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


def raw_body(response: SystemOneResponse) -> Any:
    """The wire body, which is what phase 2's replay tests want, not the parsed model."""
    http_response = response.raw_http_response
    if http_response is None:
        return response.model_dump(mode="json")
    return http_response.json()


def heading(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def describe_exception(exc: BaseException) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "class": type(exc).__name__,
        "module": type(exc).__module__,
        "mro": [base.__name__ for base in type(exc).__mro__[1:-1]],
        "str": str(exc)[:400],
    }
    for attribute in ("status", "endpoint", "request_id", "field_path"):
        if hasattr(exc, attribute):
            detail[attribute] = getattr(exc, attribute)
    body = getattr(exc, "body", None)
    if body is not None:
        detail["body"] = body
    headers = getattr(exc, "headers", None)
    if headers is not None:
        # Response headers only: nothing here carries the key we sent.
        detail["response_headers"] = {k: v for k, v in dict(headers).items() if k.lower() != "set-cookie"}
    return detail


# ---------------------------------------------------------------------------
# Probe 1 -- the three answer shapes in one request over one named-object state
# ---------------------------------------------------------------------------

THREE_QUESTIONS = {
    "is_urgent": Noul(
        instructions="Is the message urgent?",
        criteria={"true": "Needs attention now", "false": "Can wait until the next working day"},
    ),
    "team": Choice(
        instructions="Which team should handle this message?",
        criteria={
            "payments": "Charges, invoices, payment processing failures",
            "shipping": "Delivery status, delays, lost packages",
            "accounts": "Sign-in, passwords, account settings",
            "other": "None of the above",
        },
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


async def probe_shapes(client: AsyncTypeSafeClient, model: str) -> SystemOneResponse:
    heading("1. Answer shapes, over one named-object state")
    response = await client.system_one(
        state={"message": MESSAGE, "channel": "support_email"},
        questions=THREE_QUESTIONS,
        model=model,
    )
    body = raw_body(response)
    save("01_three_shapes", body)

    record("response top-level keys", sorted(body.keys()) if isinstance(body, dict) else type(body).__name__)
    record("model requested", model)
    record("model reported", response.model)
    record("model reported is versioned", response.model != model)
    record("request_id present", response.request_id is not None)
    record("request_id", response.request_id)

    noul = response.nouls["is_urgent"]
    record("noul answer (parsed)", {"type": noul.type, "noul": noul.noul})
    record("noul answer (wire)", body["answers"]["is_urgent"])
    record("noul has confidence field", "confidence" in body["answers"]["is_urgent"])

    choice = response.choices["team"]
    record("choice answer (wire)", body["answers"]["team"])
    record("choice probability key type on the wire", sorted({type(k).__name__ for k in body["answers"]["team"]["probabilities"]}))
    record("choice probabilities sum", round(sum(choice.probabilities.values()), 6))
    record("choice covers every declared option", set(choice.probabilities) == set(THREE_QUESTIONS["team"].criteria))

    score = response.scores["severity"]
    record("score answer (wire)", body["answers"]["severity"])
    record("score probability key type on the wire", sorted({type(k).__name__ for k in body["answers"]["severity"]["probabilities"]}))
    record("score probability key type after SDK parse", sorted({type(k).__name__ for k in score.probabilities}))
    record("score legend key type on the wire", sorted({type(k).__name__ for k in body["answers"]["severity"].get("legend", {})}))
    record("score legend present", "legend" in body["answers"]["severity"])
    record("score legend", score.legend)
    record("score levels are zero-based", sorted(score.probabilities) == list(range(len(THREE_QUESTIONS["severity"].criteria))))
    record("score value", score.score)
    record("answer keys equal question keys", sorted(body["answers"]) == sorted(THREE_QUESTIONS))
    return response


# ---------------------------------------------------------------------------
# Probe 2 -- usage: always reported? per request or per question?
# ---------------------------------------------------------------------------


async def probe_usage(client: AsyncTypeSafeClient, model: str, three: SystemOneResponse) -> None:
    heading("2. Usage reporting")
    one = await client.system_one(
        state={"message": MESSAGE, "channel": "support_email"},
        questions={"is_urgent": THREE_QUESTIONS["is_urgent"]},
        model=model,
    )
    save("02_usage_one_question", raw_body(one))

    record("usage on wire (three questions)", raw_body(three).get("usage"))
    record("usage on wire (one question)", raw_body(one).get("usage"))
    record("input_tokens reported", one.usage.input_tokens is not None and three.usage.input_tokens is not None)
    record("output_tokens reported", one.usage.output_tokens is not None and three.usage.output_tokens is not None)
    record(
        "usage is per request, not per question",
        f"one={one.usage.input_tokens}/{one.usage.output_tokens} three={three.usage.input_tokens}/{three.usage.output_tokens}",
    )
    record("per-answer usage field present", any("usage" in a for a in raw_body(three)["answers"].values()))


# ---------------------------------------------------------------------------
# Probe 3 -- what the state accepts
# ---------------------------------------------------------------------------


async def probe_state_types(client: AsyncTypeSafeClient, model: str) -> None:
    heading("3. State value types")
    rich_state = {
        "message": MESSAGE,
        "customers_waiting": 3,
        "is_paying_customer": True,
        "failure_rate": 1.0,
        "account": {"plan": "enterprise", "since": "2021-04-02"},
        "recent_incidents": ["2026-08-11 checkout latency", "2026-09-02 webhook backlog"],
        "nothing_here": None,
    }
    question = {
        "many_customers": Noul(instructions="Are more than two customers waiting, according to `customers_waiting`?"),
        "enterprise": Noul(instructions="Is the account on the enterprise plan, according to `account.plan`?"),
        "paying": Noul(instructions="Is this a paying customer, according to `is_paying_customer`?"),
        "prior_incidents": Noul(instructions="Has this account seen incidents before, according to `recent_incidents`?"),
    }
    for label, state in (
        ("object", rich_state),
        ("string", json.dumps(rich_state)),
        ("array", [rich_state["message"], rich_state["customers_waiting"], rich_state["account"]]),
    ):
        try:
            response = await client.system_one(state=state, questions=question, model=model)
        except TypeSafeError as exc:
            record(f"state as {label}", describe_exception(exc))
            continue
        save(f"03_state_{label}", raw_body(response))
        record(f"state as {label} accepted", {k: round(v.noul, 3) for k, v in response.nouls.items()})

    # A number that must be read as a number, not as text, to answer correctly.
    numeric = await client.system_one(
        state={"threshold": 5, "observed": 12},
        questions={"above": Noul(instructions="Is `observed` greater than `threshold`?")},
        model=model,
    )
    save("03_state_numeric", raw_body(numeric))
    record("json number read as a number", round(numeric.nouls["above"].noul, 3))


# ---------------------------------------------------------------------------
# Probe 4 -- criteria edge cases and the documented limits
# ---------------------------------------------------------------------------


async def probe_criteria_edges(client: AsyncTypeSafeClient, model: str) -> None:
    heading("4. Criteria edge cases")
    cases: dict[str, dict[str, Any]] = {
        "noul_without_criteria": {"q": Noul(instructions="Is the message urgent?")},
        "noul_true_only": {"q": Noul(instructions="Is the message urgent?", criteria={"true": "Needs attention now"})},
        "choice_null_descriptions": {"q": Choice(instructions="What is the tone?", criteria={"calm": None, "angry": None})},
        "choice_mixed_descriptions": {"q": Choice(instructions="What is the tone?", criteria={"calm": None, "angry": "Expresses frustration"})},
        "choice_two_options": {
            "q": Choice(instructions="Is this a payments issue or a shipping issue?", criteria={"payments": None, "shipping": None})
        },
        "choice_one_option": {"q": Choice(instructions="Which team?", criteria={"payments": None})},
        "choice_empty": {"q": Choice(instructions="Which team?", criteria={})},
        "score_two_levels": {"q": Score(instructions="How severe?", criteria=["Minor", "Severe"])},
        "score_one_level": {"q": Score(instructions="How severe?", criteria=["Minor"])},
        "score_empty": {"q": Score(instructions="How severe?", criteria=[])},
        "score_structured_levels": {
            "q": Score(
                instructions={"task": "Rate severity", "note": "Judge only what the message says"},
                criteria=[
                    {"level": "cosmetic", "meaning": "No impact on functionality"},
                    {"level": "degraded", "meaning": "A workaround exists"},
                    {"level": "blocking", "meaning": "No workaround exists"},
                ],
            )
        },
        "choice_many_options": {
            "q": Choice(
                instructions="Which team should handle this message?",
                criteria={f"team_{i:02d}": f"Handles topic number {i}" for i in range(60)} | {"payments": "Payment failures"},
            )
        },
        "score_many_levels": {"q": Score(instructions="How severe?", criteria=[f"Severity level {i}" for i in range(24)])},
    }
    for name, case in cases.items():
        try:
            response = await client.system_one(state={"message": MESSAGE}, questions={"q": case["q"]}, model=model)
        except TypeSafeError as exc:
            record(name, describe_exception(exc))
            save(f"04_{name}_error", describe_exception(exc))
            continue
        body = raw_body(response)
        save(f"04_{name}", body)
        record(name, body["answers"]["q"])


async def probe_limits(client: AsyncTypeSafeClient, model: str) -> None:
    heading("4b. Beyond the documented limits")
    for name, size in (("state_200k_chars", 200_000), ("state_2m_chars", 2_000_000)):
        filler = ("The quick brown fox jumps over the lazy dog. " * (size // 45))[:size]
        try:
            response = await client.system_one(
                state={"message": MESSAGE, "filler": filler},
                questions={"q": Noul(instructions="Is the message urgent?")},
                model=model,
            )
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record(name, detail)
            save(f"04b_{name}_error", detail)
            continue
        record(name, {"accepted": True, "usage": raw_body(response).get("usage")})
        save(f"04b_{name}", raw_body(response))


# ---------------------------------------------------------------------------
# Probe 5 -- model pinning
# ---------------------------------------------------------------------------


async def probe_models(client: AsyncTypeSafeClient, versioned: str) -> None:
    heading("5. Model pinning")
    for candidate in ("jev-latest", "jev-preview", versioned, "jev-does-not-exist"):
        try:
            response = await client.system_one(
                state={"message": MESSAGE},
                questions={"q": Noul(instructions="Is the message urgent?")},
                model=candidate,
            )
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record(f"model {candidate!r}", detail)
            save(f"05_model_{candidate.replace('-', '_')}_error", detail)
            continue
        record(f"model {candidate!r}", {"reported": response.model, "noul": round(response.nouls["q"].noul, 3)})


# ---------------------------------------------------------------------------
# Probe 6 -- errors
# ---------------------------------------------------------------------------


async def probe_errors(model: str) -> None:
    heading("6. Error classification")

    async with AsyncTypeSafeClient(api_key="ts-not-a-real-key", retry=RetryPolicy(max_retries=0)) as bad_client:
        try:
            await bad_client.system_one(state={"message": MESSAGE}, questions={"q": Noul(instructions="Is the message urgent?")}, model=model)
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record("wrong key", detail)
            save("06_wrong_key", detail)
        else:
            record("wrong key", "NO ERROR -- the API accepted an invalid key")

    async with AsyncTypeSafeClient(retry=RetryPolicy(max_retries=0)) as client:
        try:
            await client.system_one(state={"message": MESSAGE}, questions={}, model=model)
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record("empty questions", detail)
            save("06_empty_questions", detail)

        try:
            await client.system_one(
                state={"message": MESSAGE},
                questions={"q": {"type": "noul", "instructions": None, "criteria": {"maybe": "not a legal key"}}},  # type: ignore[dict-item]
                model=model,
            )
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record("malformed question", detail)
            save("06_malformed_question", detail)
        else:
            record("malformed question", "NO ERROR -- the API accepted it")

        try:
            await client.system_one(
                state={"message": MESSAGE},
                questions={"q": Noul(instructions="Is the message urgent?")},
                model=model,
                timeout=0.001,
            )
        except TypeSafeError as exc:
            detail = describe_exception(exc)
            record("timeout 1ms", detail)
            save("06_timeout", detail)
        else:
            record("timeout 1ms", "NO ERROR -- it answered in under a millisecond")


# ---------------------------------------------------------------------------
# Probe 7 -- retries
# ---------------------------------------------------------------------------


async def probe_retries(model: str) -> None:
    heading("7. Retries")
    default = RetryPolicy()
    record(
        "SDK default RetryPolicy",
        {
            "max_retries": default.max_retries,
            "backoff_initial": default.backoff_initial,
            "backoff_max": default.backoff_max,
            "backoff_jitter": default.backoff_jitter,
            "http_statuses": sorted(default.http_statuses),
            "respect_retry_after": default.respect_retry_after,
            "api_connection_error": default.api_connection_error,
            "api_timeout_error": default.api_timeout_error,
            "timeout": default.timeout,
        },
    )

    for label, policy in (("retry off", RetryPolicy(max_retries=0)), ("retry default", RetryPolicy())):
        started = time.perf_counter()
        async with AsyncTypeSafeClient(api_key="ts-not-a-real-key", retry=policy) as client:
            try:
                await client.system_one(state={"message": MESSAGE}, questions={"q": Noul(instructions="Is the message urgent?")}, model=model)
            except TypeSafeError as exc:
                record(
                    f"401 under {label}",
                    {"class": type(exc).__name__, "elapsed_s": round(time.perf_counter() - started, 3)},
                )

    started = time.perf_counter()
    async with AsyncTypeSafeClient(retry=RetryPolicy(max_retries=2, backoff_initial=0.1)) as client:
        try:
            await client.system_one(
                state={"message": MESSAGE},
                questions={"q": Noul(instructions="Is the message urgent?")},
                model=model,
                timeout=0.001,
            )
        except TypeSafeAPITimeoutError:
            record("timeout retried twice, elapsed_s", round(time.perf_counter() - started, 3))
        except TypeSafeError as exc:
            record("timeout under retry", describe_exception(exc))


# ---------------------------------------------------------------------------
# Probe 8 -- concurrency and batching economics
# ---------------------------------------------------------------------------


async def probe_concurrency(client: AsyncTypeSafeClient, model: str) -> None:
    heading("8. Concurrency, latency and batching")
    state = {"message": MESSAGE, "channel": "support_email"}

    started = time.perf_counter()
    single = await client.system_one(state=state, questions={"is_urgent": THREE_QUESTIONS["is_urgent"]}, model=model)
    one_question_latency = time.perf_counter() - started
    record("one question, one request, latency_s", round(one_question_latency, 3))
    record("one question, usage", {"input_tokens": single.usage.input_tokens, "output_tokens": single.usage.output_tokens})

    started = time.perf_counter()
    batched = await client.system_one(state=state, questions=THREE_QUESTIONS, model=model)
    batched_latency = time.perf_counter() - started
    record("three questions, one request, latency_s", round(batched_latency, 3))
    record("three questions batched, usage", raw_body(batched).get("usage"))

    started = time.perf_counter()
    separate = await asyncio.gather(
        *(client.system_one(state=state, questions={key: question}, model=model) for key, question in THREE_QUESTIONS.items())
    )
    separate_latency = time.perf_counter() - started
    record("three questions, three concurrent requests, latency_s", round(separate_latency, 3))
    record(
        "three separate requests, summed usage",
        {
            "input_tokens": sum(r.usage.input_tokens or 0 for r in separate),
            "output_tokens": sum(r.usage.output_tokens or 0 for r in separate),
        },
    )
    record("same client shared across gather without error", True)

    started = time.perf_counter()
    fan_out = await asyncio.gather(
        *(client.system_one(state=state, questions=THREE_QUESTIONS, model=model) for _ in range(8)),
        return_exceptions=True,
    )
    failures = [describe_exception(r) for r in fan_out if isinstance(r, BaseException)]
    record("eight concurrent requests on one client, failures", failures or "none")
    record("eight concurrent requests, latency_s", round(time.perf_counter() - started, 3))
    save("08_batched", raw_body(batched))


# ---------------------------------------------------------------------------
# Probe 9 -- stability, which sets the live tests' margins
# ---------------------------------------------------------------------------


async def probe_stability(client: AsyncTypeSafeClient, model: str, repeats: int = 8) -> None:
    heading("9. Stability across repeats")
    state = {"message": MESSAGE, "channel": "support_email"}
    responses = await asyncio.gather(*(client.system_one(state=state, questions=THREE_QUESTIONS, model=model) for _ in range(repeats)))
    save("09_stability", [raw_body(r) for r in responses])

    nouls = [r.nouls["is_urgent"].noul for r in responses]
    choices = [r.choices["team"].choice for r in responses]
    choice_probabilities = [r.choices["team"].probabilities["payments"] for r in responses]
    scores = [r.scores["severity"].score for r in responses]

    record("noul values", [round(v, 4) for v in nouls])
    record("noul spread", round(max(nouls) - min(nouls), 4))
    record("noul stdev", round(statistics.pstdev(nouls), 4) if repeats > 1 else 0.0)
    record("choice verdicts", sorted(set(choices)))
    record("choice verdict stable", len(set(choices)) == 1)
    record("choice probability spread", round(max(choice_probabilities) - min(choice_probabilities), 4))
    record("score values", [round(v, 4) for v in scores])
    record("score spread", round(max(scores) - min(scores), 4))
    record("bit-identical responses", len({json.dumps(raw_body(r)["answers"], sort_keys=True) for r in responses}) == 1)


# ---------------------------------------------------------------------------
# Probe 10 -- the same call with the httpx already in the core
# ---------------------------------------------------------------------------


async def probe_plain_httpx(model: str, api_key: str) -> None:
    heading("10. The same call over plain httpx")
    payload = {
        "state": {"message": MESSAGE, "channel": "support_email"},
        "model": model,
        "questions": {
            "is_urgent": {
                "type": "noul",
                "instructions": "Is the message urgent?",
                "criteria": {"true": "Needs attention now", "false": "Can wait until the next working day"},
            },
            "team": {
                "type": "choice",
                "instructions": "Which team should handle this message?",
                "criteria": {
                    "payments": "Charges, invoices, payment processing failures",
                    "shipping": "Delivery status, delays, lost packages",
                    "accounts": "Sign-in, passwords, account settings",
                    "other": "None of the above",
                },
            },
            "severity": {
                "type": "score",
                "instructions": "How severe is the reported issue?",
                "criteria": [
                    "Cosmetic; no impact on functionality",
                    "A feature is degraded, but a workaround exists",
                    "Blocking issue; no workaround exists",
                ],
            },
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        started = time.perf_counter()
        http_response = await client.post(
            f"{BASE_URL}/v1/systemone",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        elapsed = time.perf_counter() - started
        record("plain httpx status", http_response.status_code)
        record("plain httpx latency_s", round(elapsed, 3))
        record("response headers", {k: v for k, v in http_response.headers.items() if "request" in k.lower() or "id" in k.lower()})
        body = http_response.json()
        save("10_plain_httpx", body)
        record("plain httpx body keys", sorted(body))
        record("plain httpx answers match the SDK's shape", sorted(body["answers"]) == sorted(THREE_QUESTIONS))

        bad = await client.post(
            f"{BASE_URL}/v1/systemone",
            json=payload,
            headers={"Authorization": "Bearer ts-not-a-real-key", "Content-Type": "application/json"},
        )
        record("plain httpx, wrong key", {"status": bad.status_code, "body": bad.json()})
        save("10_plain_httpx_wrong_key", {"status": bad.status_code, "body": bad.json()})


async def list_models(api_key: str) -> str:
    heading("0. Models")
    async with httpx.AsyncClient(timeout=30.0) as client:
        http_response = await client.get(f"{BASE_URL}/v1/models", headers={"Authorization": f"Bearer {api_key}"})
        record("GET /v1/models status", http_response.status_code)
        if http_response.status_code != 200:
            record("GET /v1/models body", http_response.text[:400])
            return "jev-latest"
        body = http_response.json()
        save("00_models", body)
        record("models", body)
        entries = body.get("data", body.get("models", []))
        names = [e.get("name", e.get("id")) if isinstance(e, dict) else e for e in entries]
        record("model names listed", names)
        versioned = [name for name in names if name not in {"jev-latest", "jev-preview"}]
        record("a versioned (non-alias) id is listed", bool(versioned))
        pinned = versioned[0] if versioned else "jev-latest"
        record("id chosen for the pinning probe", pinned)
        return pinned


async def main() -> None:
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise SystemExit(NO_KEY)
    record("key length", len(api_key))

    versioned = await list_models(api_key)

    async with AsyncTypeSafeClient(retry=RetryPolicy(max_retries=0), timeout=60.0) as client:
        three = await probe_shapes(client, "jev-latest")
        await probe_usage(client, "jev-latest", three)
        await probe_state_types(client, "jev-latest")
        await probe_criteria_edges(client, "jev-latest")
        await probe_limits(client, "jev-latest")
        await probe_models(client, versioned)
        await probe_concurrency(client, "jev-latest")
        await probe_stability(client, "jev-latest")

    await probe_errors("jev-latest")
    await probe_retries("jev-latest")
    await probe_plain_httpx("jev-latest", api_key)

    heading("Summary")
    save("99_findings", [{"label": label, "value": value} for label, value in findings])
    print(f"{len(findings)} findings, written to {RESPONSES_DIR / '99_findings.json'}")


if __name__ == "__main__":
    asyncio.run(main())
