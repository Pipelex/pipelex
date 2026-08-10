# Fix: `Date` and `Time` natives cannot be produced by a live `PipeLLM`

Bug report: `wip/native-date-time-live-run.md` — **verified 2026-08-10**, reproduced locally without any LLM call. Branch: `fix/Native-date-time`.

## Root cause (established, do not re-derive)

A live `PipeLLM` with `output = "Date"`, `Date[]`, or `Time` fails pydantic validation on the model's response, while `YesNo` works and the `inputs.json` path accepts the identical strings. Three facts combine:

1. **Instructor validates structured outputs in strict mode by default.** Every instructor `create`/`create_with_completion` signature has `strict: bool = True` (instructor 1.15.1: `instructor/core/patch.py:151`, `instructor/core/client.py`), and pipelex's workers never pass `strict` — see `pipelex/providers/openai/openai_completions_llm_worker.py:223` (`create_with_completion` call) and the sibling workers (anthropic, mistral, google, bedrock, openai_responses). So the response JSON is validated with `strict=True` regardless of mode (`parse_tools`, `parse_anthropic_json`, … in `instructor/processing/function_calls.py` all call `model_validate_json(..., strict=strict)`).
2. **Strict JSON mode would normally be fine** — pydantic strict *JSON* validation accepts ISO strings for `date`/`time` fields (JSON has no temporal type). Plain `datetime.date` fields in user structures survive strict. This is why only the temporal natives break.
3. **A `mode="before"` field validator disables that JSON-input string acceptance.** The value returned by the before-validator is re-validated as Python input, where strict rejects `str` with `date_type`/`time_type` (the exact reported error codes). Proven with a minimal pair: `class Plain(BaseModel): date: datetime.date` passes `model_validate_json('{"date":"2025-03-12"}', strict=True); adding a no-op `@field_validator("date", mode="before")` makes the same call fail. The before-validators on `DateContent` and `TimeContent` (named `_reject_lax_temporal` at the time of this diagnosis, `_validate_temporal` since the fix) were the only ones on non-JSON-native fields among the natives (`JSONContent`'s is on a `dict[str, Any]`, immune). `YesNoContent` has no before-validator and `bool` is a JSON type — hence the control passing.

Also verified: field-level `Field(strict=False)` does **not** override the call-level `strict=True` (tested; call-level wins), so there is no one-liner escape.

Repro (no network):

```python
DateContent.model_validate_json('{"date": "2025-03-12", "time": "14:00:00+00:00"}', strict=True)
# 2 validation errors: date_type on 'date', time_type on 'time' — identical to the live-run failure
TimeContent.model_validate_json('{"time": "14:00:00+00:00"}', strict=True)   # time_type
DateContent.model_validate({"date": "2025-03-12"})                            # lax: passes (the inputs.json path)
```

## Chosen fix — make the temporal natives validation-mode-proof (model-side, surgical)

Have the before-validators **finish the job**: after the existing rejection guards, parse a `str` into the real `datetime.date`/`datetime.time` via `fromisoformat`, so the inner validation always receives an already-correct Python object and passes under strict Python, strict JSON, and lax alike. Verified experimentally: strict JSON, strict Python, lax, object passthrough, UTC-offset preservation (`14:00:00+00:00` → `tzinfo=UTC`), and `Z` suffix all work.

Explicitly rejected alternative: passing `strict=False` to instructor in every worker. Blast radius spans all providers and all user structures (would re-open the silent lax coercions on LLM outputs that strict currently blocks, and weaken instructor's re-ask signal). The natives fix is the smallest correct surface; strict stays the inference-path policy.

Guard-ordering constraint (matters, keep tested): the numeric-string epoch guard must run **before** parsing — `datetime.date.fromisoformat` happily accepts basic-format `"20250312"`, which the DT6 guard must keep rejecting as an epoch-looking number.

## Tasks

- [x] Verify the bug report (done — see root cause above)
- [x] **`pipelex/core/stuffs/date_content.py`** — in `_reject_lax_temporal`, after the existing guards (datetime object, int/float/numeric-string epoch, datetime-shaped string on `date`), parse remaining `str` values: `datetime.date.fromisoformat` for `date`, `datetime.time.fromisoformat` for `time`. Wrap the `fromisoformat` `ValueError` in a clear message naming the field and the ISO 8601 expectation (must stay `ValueError` so pydantic wraps it into a `ValidationError`). Non-str values (real `date`/`time` objects, e.g. from `--mock-inputs`) pass through unchanged. Rename the validator (`_validate_temporal` or similar) — it no longer only rejects — and update its comment to state the second purpose: returning a real object is what keeps the model valid under the strict validation instructor applies to LLM responses (a before-validator forfeits pydantic's strict-JSON ISO-string acceptance).
- [x] **`pipelex/core/stuffs/time_content.py`** — same change for `TimeContent.time`. Note: `fromisoformat` also closes the numeric-string hole (`"3600"`) that this class's guards never covered (DateContent guarded it, TimeContent didn't — flagged in the report as an asymmetry; decide whether to add the explicit epoch guard for the nicer message, mirroring DateContent).
- [x] **Tests — red first** (`tests/unit/pipelex/core/stuffs/date_content/`, `.../time_content/`): a strict-mode module simulating the instructor path. Cases:
  - `DateContent.model_validate_json(..., strict=True)` with date-only and date+time payloads — the exact reported inputs (`"2025-03-12"`, `"14:00:00+00:00"`)
  - `TimeContent.model_validate_json(..., strict=True)` — offset preserved on `tzinfo` (fidelity), plus `Z` suffix and fractional seconds
  - strict **Python**-mode (`model_validate(..., strict=True)`) for both — instructor modes that validate parsed dicts
  - the generated list wrapper (the reported `ListOfDateContent` case): build it via `stuff_content_factory` list-class generation and validate a two-item payload under strict JSON — *shipped differently, see the decision below: that wrapper is built inline in `llm_generate.py`, not by the factory, so the tests mirror that shape*
  - real `date`/`time` objects still accepted under strict (mock-inputs path)
  - all existing rejections still fire in **both** modes: `86400`, `"86400"`, `"8.64e4"`, `"20250312"` (epoch-lookalike, must NOT be parsed), `datetime` object, `"2026-07-07T00:00:00"` on `date`
  - malformed string (`"not-a-date"`) → `ValidationError` with the clear message
- [x] Existing lax-path tests stay green (`test_date_content_serialization.py`, `test_time_content.py`, factory/input-shaper tests)
- [x] `make agent-check`
- [x] `make agent-test`
- [x] **CHANGELOG.md** — `[Unreleased]`, bold-label style: `Date`/`Time` natives failed every live structured-output run (strict-mode validation of the LLM's ISO strings); now parse ISO 8601 in their validators so strict and lax paths agree.
- [x] **Docs** — check `docs/` pages describing the `Date`/`Time` natives for anything stating the accepted forms; update if the parsing behavior is documented. No new page needed.

## Decisions taken while implementing

- **`TimeContent` got the explicit numeric-string guard** (the flagged asymmetry). Not just for the message: `datetime.time.fromisoformat` accepts the basic form, so without the guard `"154000"` would newly parse as `15:40:00` — the DT6 hole the parsing step would otherwise open. Same guard-before-parse ordering as `DateContent`.
- **The numeric-string predicate moved to `pipelex/tools/misc/string_utils.py`** as `is_numeric_string` (it was private to `date_content.py`), since both temporal natives need it and neither should depend on the other. Its temporal (DT6) rationale stays in the two validators' comments, where it belongs.
- **The list-wrapper test declares the wrapper inline.** The reported `ListOfDateContent` is built inline in `pipelex/cogt/content_generation/llm_generate.py`, not by `stuff_content_factory` — so the test mirrors that shape (`items: list[DateContent]`) rather than reaching for a factory that does not generate it.
- **No `docs/` change.** The pages describing `Date`/`Time` (`native-concepts.md`, `provide-inputs.md`) document the ISO 8601 forms accepted and the rendering, both unchanged by the fix — the model-side path simply now honors what they already state.
- **~~The model layer stays looser than the input layer on exotic ISO forms.~~ Reversed after review** (see below): both layers now share one extended-ISO parser.

## Review round 1 — what the bots found and what was done

Greptile: clean (5/5). Codex: one finding. cubic: four. Verdicts, each verified by probe:

- **`24:00` is silently accepted on Python 3.14 (codex, P2) — REAL, fixed.** `time.fromisoformat("24:00:00")` returns `00:00:00` on 3.14 but raises on 3.11-3.13, and `requires-python` is `>=3.11,<3.15` — so `{"date":"2025-03-12","time":"24:00:00"}` would land as March 12 midnight instead of March 13's, on part of the supported range only. Now rejected explicitly, ahead of the parser, with a message naming the end-of-day meaning. Verified by running the new module under both 3.13 and 3.14: identical behavior.
- **Basic-format and week/ordinal forms reach the models (cubic, P2/P2/P3) — REAL as a contract split, fixed together.** Not corruption (the parsed values were correct), but `StuffContentFactory` pinned authored inputs to *extended* ISO while the new model path accepted `"2026-W27-2"`, `"2026-189"`, `"154000+00:00"`. One native, two accepted vocabularies. Fixed by extracting `pipelex/core/stuffs/iso_temporal.py` — `parse_iso_date` / `parse_iso_time`, owning the extended pin and the 24:00 rejection — and having the models *and* the factory use it. The factory's duplicated regex is gone, and its `_make_time_content` inherited the 24:00 fix it had the same bug in.
- **`is_numeric_string` also matches `nan`/`inf`/`1_000` (cubic, P3) — DECLINED.** The observation is true but cosmetic: those inputs are rejected either way, only under the "no epoch-seconds" message rather than the malformed-ISO one, and no model emits them.

  *Corrected in round 3, after cubic rightly challenged the original reasoning.* The first version of this note claimed switching to `int()` would "reopen the exponent/decimal epoch hole" and fail `test_numeric_string_is_rejected`. That was wrong: with the extended-ISO shape pin now sitting in front of the parse, a string `int()` declines falls through to the parser and is rejected there anyway, and the test asserts only that a `ValidationError` is raised. Nothing would be reopened and the suite would stay green. The honest reason to decline is narrower — `is_numeric_string` now only selects *which* rejection message appears, and `int()` would make the accurate "no epoch-seconds" message stop covering the exponent and decimal epoch forms (`8.64e4`, `86400.0`), which is a small step backwards for no gain.

## Review round 2 — the unification was incomplete

Nine findings across greptile, codex and cubic; four of them named one real gap, and the probes settled the rest.

- **The combined authored datetime bypassed the shared parser (codex P2, cubic P2×2, greptile P1) — REAL, fixed.** Round 1 routed `_make_time_content` through `parse_iso_time` but left `_parse_iso_temporal` handing the whole string to `datetime.fromisoformat`, so `"2026-07-07T154000"` was accepted on the authored path while `{"date": "2026-07-07", "time": "154000"}` was refused on the model path — the contract split the round-1 message claimed to have closed. It now splits the string and sends each half to `parse_iso_date` / `parse_iso_time`, which is what makes the time half reachable at all. That also makes the end-of-day form uniform: previously `"2026-07-07T24:00:00"` raised on 3.11-3.13 and parsed on 3.14 (correctly rolling to the 8th, so no corruption — greptile's "same day's midnight" claim was wrong), and it is now rejected everywhere.
- **The offset pattern still allowed the basic `±hhmm` (greptile P1, cubic P3) — REAL, fixed.** `15:40:00+0200` slipped through the "extended only" pin, inherited from the factory's old regex. Tightened to `Z` / `±hh` / `±hh:mm`; `+02` stays because hour-only *is* an extended spelling.
- **The comma fraction separator was rejected (codex P2, cubic P2) — REAL, fixed.** ISO 8601 allows `15:40:00,500` and `fromisoformat` parses it; the round-1 regex only allowed `.`, so the pin was narrower than the standard it named. One character.
- **Whitespace was normalized on one side only (cubic P3) — REAL, fixed.** The parsers stripped their input while the factory validated the raw text, so padding was accepted from a model and refused from an author. The parsers now validate the text as given, and padding is refused on both.
- **Sub-microsecond precision is truncated (cubic P1) — DECLINED.** True (`15:40:00.1234567` → `…123456`), but `datetime.time` cannot represent more, so the only alternative is failing a live run over precision no source states. Truncating to what the type holds is what every Python consumer does; the natives' fidelity rules are about not fabricating or shifting a value, not about sub-microsecond rounding.

## Review round 3

- **An out-of-range offset minute was silently normalized (codex P2, cubic P2) — REAL, fixed.** `15:40:00+02:60` arrived as `+03:00`: the offset components are summed into a `timedelta`, so nothing range-checks the minutes (the offset *hour* does raise, and the time's own minute/second are checked by `fromisoformat`). A stated offset silently becoming a different one is exactly the fidelity loss this native exists to prevent. Offset minutes are now pinned to `[0-5]\d`.
- **The round-1 declined-reason was factually wrong (cubic P3) — accepted, note corrected in place.** The decision stands; the reasoning behind it did not survive scrutiny. See the corrected bullet above.

## Review round 4

- **The pattern admitted a lower-case `z` the parser refused (codex P2, cubic P3) — REAL, fixed by honoring the pattern.** `[Zz]` matched `15:40:00z`, but `time.fromisoformat` takes only the upper-case designator, so the value fell through to the generic "not a valid ISO 8601" message. The two bots proposed opposite remedies — normalize it, or drop `z` from the pattern. Chose to admit it: pydantic accepted `z` before this parser existed (verified), so dropping it would regress the live LLM path this PR exists to unblock, and RFC 3339 states the two spellings name the same offset. Case-folding a designator is not normalizing the value the way trimming padding would be, so it does not contradict the round-2 decision to validate the text as given.

## Follow-ups (out of this repo, after release)

- [ ] `mthds-ui` (branch `feature/Native-concepts_stories`): `make fixtures-live ONLY=pipeline_32` to replace the placeholder LIVE fixture with real data — the natural end-to-end regression check named in the bug report. Gated on a released pipelex version carrying this fix.
- [ ] Optional live sanity check before release: run a gateway `PipeLLM` with `output = "Time"` / `Date[]` (the repro in the report) to confirm the production path.

## Cold-start pointers

- Failing call chain: `PipeLLM._run_operator_pipe` → `run_llm_object` (`pipelex/pipe_operators/llm/pipe_llm.py`) → worker `_gen_object` → instructor `create_with_completion(response_model=schema, ...)` → `function_calls.py` parse → `model_validate_json(..., strict=True)`.
- Gateway model config is fetched remotely (`pipelex/kit/configs/inference/backends/pipelex_gateway.toml` only allows `sdk`/`structure_method` overrides); the failing run used the openai-compatible gateway completions path, but the fix is mode-agnostic and provider-agnostic.
- Instructor pin: 1.15.1 (`.venv/lib/python3.13/site-packages/instructor/`).
