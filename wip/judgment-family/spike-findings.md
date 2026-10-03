---
status: draft
item: L-260919-3aeab8
---

# TypeSafe System One — what the judgment worker may rely on

Everything below was observed against the live API on 2026-09-19 from `wip/judgment-family/spike/typesafe_async_spike.py` and `typesafe_followups_spike.py`, with `typesafe-sdk` 0.7.0 answering as `jev-1.13.0`. Every successful response is saved under `spike/responses/` as the **wire body**, taken from `raw_http_response.json()` and never from the SDK's `model_dump`, so a replay test checks the SDK against the API rather than against itself; phase 2's unit tests replay those files rather than calling the API. A refusal is saved as a `describe_exception` envelope instead, with the wire body nested under `body` beside the SDK's class name and the response headers — a fixture for the error classification, not a response to parse. Nothing saved carries the key, a request header, or any value derived from the key. Where an observation contradicts what `design.md` recorded from the documentation, the design has been corrected in the same change and the contradiction is listed under "Where the design was wrong".

**Verdict: go, with the SDK.** The reasons are in the last two sections.

## Answer shapes

A response body has exactly three top-level keys, `answers`, `model` and `usage`. `answers` is keyed by the question ids the request supplied, and the keys come back identical — the worker can map them back without a fallback.

A yes/no answer is `{"type": "noul", "noul": <float 0..1>}` and carries no confidence field, exactly as the design assumed: the probability is the confidence.

A choice answer is `{"type": "choice", "choice": <option key>, "confidence": <float>, "probabilities": {<option key>: <float>}}`. The distribution covers every declared option, including the ones at zero, and sums to 1. Its keys are the author's own option keys, as strings, on the wire and after parsing alike.

A rating answer is `{"type": "score", "score": <float>, "confidence": <float>, "legend": {...}, "probabilities": {...}}`. `legend` is always present and echoes the level descriptions back verbatim — including structured ones, if the criteria were structured. `score` is the probability-weighted position over zero-based level indices and may fall between levels.

**The one shape trap.** `probabilities` and `legend` on a rating answer are keyed by **strings on the wire** (`"0"`, `"1"`, `"2"`) and by **integers after the SDK parses them**, because `ScoreAnswer` declares `dict[int, ...]` and pydantic coerces. A hand-written `httpx` worker would receive strings and have to convert them itself. The replay fixtures in `spike/responses/` hold the wire form, so a unit test that feeds them through the SDK's models sees ints and one that reads the JSON directly sees strings.

## Usage and cost

`usage.input_tokens` and `usage.output_tokens` were reported on every successful call, and no answer carries a usage field of its own: usage is per request, never per question. Both grow with the number of questions. One state, asked 1, 5, 20 and 50 yes/no questions, gave 323/22, 387/94, 637/364 and 1147/904 input/output tokens — so input grows sublinearly, since the state is paid for once, and output grows roughly linearly with the questions. (A second, longer state gave 354/23 for one question and 506/78 for three; the two series are over different states and must not be mixed.)

The models page prices input at $0.042 per million tokens and **output at zero**. The cost report must therefore price output tokens at zero rather than at an output rate, which is the one place the judgment family's cost arithmetic differs from an LLM's. A typical judgment is a few hundred input tokens, so a full live-test run costs a fraction of a cent; cost is not a reason to keep the live tests thin.

Both `Usage` fields are `Optional` in the SDK's model and defaulted to `None`, so the worker must tolerate their absence even though they were always present here.

## What the state accepts

A JSON object state and the same object serialised to a JSON string gave the same answers to the same four questions, within the model's own rounding. An **array** state gave materially worse answers — the question "are more than two customers waiting, according to `customers_waiting`?" fell from 0.96 to 0.54 — because an array drops the field names the question refers to.

A JSON **number** is read as a number: a state of `{"threshold": 5, "observed": 12}` answered "is `observed` greater than `threshold`?" at 0.99. Booleans, nested objects, arrays inside an object, and `null` values were all accepted and all read correctly through backticked paths.

**This settles the design's state-building question in the design's favour.** The kernel's state builder should send a JSON object keyed by input name, with a `Number` input as a JSON number and a `YesNo` as a JSON boolean, rather than rendering everything to text. It must not send a bare array.

## Criteria, and the limits that are real

A yes/no question needs `instructions` or `criteria`; with neither — or with an empty `instructions` string — the API answers 400. Both `true` and `false` criteria are individually optional, and supplying only one works. An **unknown criteria key is silently ignored**: `{"maybe": "who knows"}` returned the same 0.11 as no criteria at all, so a typo in a criteria key fails silently and our blueprint must be the thing that catches it.

`instructions` and `criteria` accept structured JSON, not only strings — a rating with object-shaped levels was accepted and echoed those objects back in the legend. The operator surface needs only strings, so this is headroom, not a requirement.

The API's own minimums are looser than the design's: a choice with **one** option and a rating with **one** level were both accepted and answered. An empty choice criteria map is a 400 from the server, and an empty rating criteria list is refused by the SDK before any HTTP call. The design's "at least two options, at least two levels" is therefore our rule and not the vendor's, which is the right place for it — a one-option choice is a question with no question in it.

**A rating is capped at ten levels**, and the boundary was probed rather than read off the refusal's wording: ten levels are accepted, eleven are refused with `400 "Too many score levels. Must have at most 10 levels."` This is the vendor's limit and not the language's, so by the design's own rule in Part 5 the **worker** enforces it, not the blueprint — which means an eleven-level method stays legal MTHDS that this one backend refuses, and a second backend could accept it. A choice took 61 options without complaint.

Worth noting for the authoring guidance: the ten-level rating answered with a confidence of 0.54 and a distribution spread across four levels, against 1.0 and a single level for the three-level scale over the same material. A long scale of thin, formulaic levels buys resolution the model cannot actually supply, which is the vendor's own advice that levels must describe concrete situations, seen from the other side.

The context limit is 64k tokens per request, 32k for the state plus the longest question. A 200k-character state is refused with `400 {"detail": {"error_type": "max_tokens_exceeded"}}`.

## Model pinning

`GET /v1/models` lists **only the two aliases**, `jev-latest` and `jev-preview`, with descriptions and release dates and no versioned id anywhere in the body. Both aliases currently resolve to `jev-1.13.0`, and preview is byte-identical to latest today.

The versioned id `jev-1.13.0` **is accepted** as a request `model` and is reported back unchanged, so the deck can pin a versioned handle as the design intends. But it is discoverable only from the models documentation page, never from the API: no truncation works either (`jev-1.13`, `jev-1` and `jev` are all `400 Unknown model`). Moving the pin at the next release is therefore a documentation read, not a programmatic lookup, and the deck comment should say so.

An unknown model is `400 {"error_type": "api_usage_error", "message": "Unknown model: …"}`, not a 404.

## Errors — the design's biggest correction

**Every validation failure observed returned `400`, never the `422` the documentation advertises.** The design's error classification was written against `401/422/429/529` and must be rewritten around `400`. What was actually seen:

| What was sent | Status | SDK exception | Body |
| --- | --- | --- | --- |
| An invalid API key | 401 | `TypeSafeAuthenticationError` | `{"detail": {"error_type": "authentication_error", "message": …}}` |
| A yes/no question with neither instructions nor criteria | 400 | `TypeSafeBadRequestError` | `{"detail": "Noul question must have criteria or instructions: q"}` |
| A choice with no options | 400 | `TypeSafeBadRequestError` | `{"detail": "Choice question must have at least one choice: q"}` |
| Eleven rating levels (ten are accepted) | 400 | `TypeSafeBadRequestError` | `{"detail": "Too many score levels. Must have at most 10 levels."}` |
| A 200k-character state | 400 | `TypeSafeBadRequestError` | `{"detail": {"error_type": "max_tokens_exceeded"}}` |
| An unknown model name | 400 | `TypeSafeBadRequestError` | `{"detail": {"error_type": "api_usage_error", "message": …}}` |
| A 1 ms timeout | — | `TypeSafeAPITimeoutError` | no response |

**The error body has two shapes, and the worker must read both.** `detail` is a bare string for the question-shape errors and an object carrying `error_type` and sometimes `message` for the rest. The `error_type` values seen are `authentication_error`, `api_usage_error` and `max_tokens_exceeded`. Classifying on the HTTP status alone cannot separate "the author wrote an illegal question" from "the state is too big" from "the deck names a model that does not exist", all three of which are 400; the worker should branch on `error_type` where it is present and fall back to the status.

**Two failure classes, not one.** The SDK raises a bare `TypeSafeError` — no status, no body, no request id — for what it validates client-side before sending: an empty questions map (`"At least one question is required."`) and a rating with no criteria. Everything reaching the server raises a `TypeSafeAPIError` subclass carrying `status`, `body`, `headers`, `endpoint` and `request_id`. The worker's classification needs an arm for each, and the bare one is a Pipelex bug rather than a vendor failure, since our blueprint validation should have caught it first.

`request_id` is present on **success** too, read from the `x-typesafe-request-id` header, and every log line the worker writes should carry it rather than only the failures. But the two paths need **two different accessors**, and this is a trap the worker must not walk into: on a response, `request_id` is a property that **raises `TypeSafeError`** when the header was absent rather than returning `None`, and so is `raw_http_response`; on a `TypeSafeAPIError` the same attribute is declared `str | None` and is safe to read unguarded. So the success path reads it inside a `try`, and the error path reads it plainly. The spike's own first run recorded `request_id is not None`, which could only ever be `True` or raise — a tautology, now fixed to a guarded read.

Neither `429` nor `529` was provoked: 40 concurrent requests finished in 0.77 s with no failure, against documented limits of 1200 requests per minute and 250k tokens per second.

## Retries

The SDK's default `RetryPolicy` is `max_retries=2`, `backoff_initial=0.5`, `backoff_max=5.0`, `backoff_jitter=0.25`, `respect_retry_after=True`, its own `timeout=30.0`, and it retries on 408, 429 and every status from 500 to 599, plus connection and timeout errors. It does **not** retry a 401, which was confirmed by the failure arriving in the same half second with retries on and off.

`RetryPolicy(max_retries=0)` turns it off completely, and a policy passed per call overrides the client's. Retry behaviour can therefore be a Pipelex decision recorded in one place, as the design requires. Note that `RetryPolicy` carries a `timeout` of its own beside the client's and the per-call one — the worker should set all three deliberately rather than leave two at the SDK's defaults.

## Concurrency and why the contract is batch-shaped

One `AsyncTypeSafeClient` served 8 and then 40 concurrent `system_one` calls through `asyncio.gather` with no failure and no interference, so caching the client in the `SdkClientRegistry` is safe.

A single request answers in about 0.24 s from this machine — not the "roughly a tenth of a second" the design took from the documentation, which is presumably measured closer to the service.

**The batching economy is real and large.** Three questions over one state cost 506 input tokens in one request and 1138 across three concurrent requests, and took 0.27 s against 0.66 s. Fifty questions in one request still answered in 0.27 s. Decision 6 — a batch-shaped worker contract with the operator sending a batch of one — is justified, and a later operator that asks several questions at once will get better than a 2× saving for doing so.

## Stability, and the margins the live tests should use

Probabilities come back quantised to two decimals. On an unambiguous case, eight repeats were **bit-identical** — same 0.98, same verdict, same 2.0 rating. On a deliberately borderline case, ten repeats moved the yes/no probability across 0.11 and 0.12, a spread of 0.01 with a standard deviation of 0.003; the choice verdict never changed and its confidence sat between 0.93 and 0.96; the rating did not move at all.

**So the live tests may assert verdicts exactly** — the chosen option, the yes/no side of the threshold, the rating level — **and should give a probability a margin of ±0.05**, which is fifteen times the observed noise and still tight enough to catch a real regression.

The far larger source of movement is the question's own wording: rewording "is the message urgent?" to "does this message need attention today?" moved the same case from 0.11 to 0.30. Live tests must pin their exact instruction strings, and a test that fails after an innocuous-looking wording edit is telling the truth.

## The dependency in this repo

`uv add --optional typesafe "typesafe-sdk>=0.7.0"` added exactly five packages — `typesafe-sdk`, `httpx2`, `httpcore2`, `httpx2-jsfetch` and `truststore` — and moved nothing else in the lock. The SDK's `pydantic>=2.12.0` floor is already satisfied by the 2.13.4 the repo resolves, so pydantic did not move and the floor only ever binds an install that takes the extra.

`httpx2` coexists with the core's `httpx` without incident; they are separate top-level modules and the spike imports both in one process. `make agent-check` passed in full — pyright 0 errors, mypy no issues across 2740 source files — so **the new typed dependency did not change either checker's reading of any unrelated import**, which was the specific risk the plan raised. `make agent-test` passed in full.

One piece of friction worth knowing before phase 2: ruff runs over `.` with `select = ["ALL"]`, so scratch scripts under `wip/` are linted like product code. The two spike scripts carry a file-level ignore for the namespace-package rule and were otherwise written to pass.

## Verdict: go, and use the SDK

**Go.** The API does what the design needs. The three question types map cleanly onto the three verdict shapes, the answers carry their uncertainty, batching is cheap, one client is safe to share, and the model is stable enough to test against live.

**Use the SDK, not a hand-written POST.** This closes the design's open question on the vendor dependency. The SDK earns its place three times over: it maps status onto typed exception classes carrying `status`, `body`, `endpoint` and `request_id`, which is precisely the input the worker's error classification needs and which a bare `httpx` call would make us rebuild; it coerces the rating answer's string keys to integers, which is otherwise our job; and its `RetryPolicy` is explicit, inspectable and fully disableable, so retry stays a decision we record rather than a default we inherit. The feared cost did not materialise: five additive packages behind an optional extra, no lock movement, no type-checker disturbance, both suites green.

A plain `httpx` worker was written and run in the spike (`probe_plain_httpx`) and does work — the wire is simple enough — so this is a judgement about what the worker would have to rebuild, not about whether it could.

## Where the design was wrong

Each of these has been corrected in `design.md`.

- **Validation failures are `400`, not `422`.** The documented `422` was never seen.
- **The error body has two shapes**, a bare-string `detail` and an object `detail` carrying `error_type`; the design assumed one.
- **A rating is capped at ten levels**, probed at the boundary: ten accepted, eleven refused. The design recorded "a bounded number" without the number. Being the vendor's limit, it is the worker's to enforce, per Part 5.
- **The API's minimums are one option and one level**, not two; our stricter rule is ours.
- **An unknown yes/no criteria key is ignored silently**, so the blueprint must catch it.
- **`/v1/models` lists only aliases.** A versioned id is requestable but is not discoverable from the API.
- **A rating answer's `probabilities` and `legend` keys are strings on the wire**, integers only after the SDK parses them.
- **`usage` is per request**, and output tokens are free, so the cost report prices them at zero.
- **Latency is about 0.24 s from here**, not 0.1 s.
- **An array state degrades answers** badly enough that the state builder must always send an object.
