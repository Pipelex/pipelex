# Fix: `Date` and `Time` natives cannot be produced by a live `PipeLLM`

Bug report: `wip/native-date-time-live-run.md` — **verified 2026-08-10**, reproduced locally without any LLM call. Branch: `fix/Native-date-time`.

## Root cause (established, do not re-derive)

A live `PipeLLM` with `output = "Date"`, `Date[]`, or `Time` fails pydantic validation on the model's response, while `YesNo` works and the `inputs.json` path accepts the identical strings. Three facts combine:

1. **Instructor validates structured outputs in strict mode by default.** Every instructor `create`/`create_with_completion` signature has `strict: bool = True` (instructor 1.15.1: `instructor/core/patch.py:151`, `instructor/core/client.py`), and pipelex's workers never pass `strict` — see `pipelex/providers/openai/openai_completions_llm_worker.py:223` (`create_with_completion` call) and the sibling workers (anthropic, mistral, google, bedrock, openai_responses). So the response JSON is validated with `strict=True` regardless of mode (`parse_tools`, `parse_anthropic_json`, … in `instructor/processing/function_calls.py` all call `model_validate_json(..., strict=strict)`).
2. **Strict JSON mode would normally be fine** — pydantic strict *JSON* validation accepts ISO strings for `date`/`time` fields (JSON has no temporal type). Plain `datetime.date` fields in user structures survive strict. This is why only the temporal natives break.
3. **A `mode="before"` field validator disables that JSON-input string acceptance.** The value returned by the before-validator is re-validated as Python input, where strict rejects `str` with `date_type`/`time_type` (the exact reported error codes). Proven with a minimal pair: `class Plain(BaseModel): date: datetime.date` passes `model_validate_json('{"date":"2025-03-12"}', strict=True); adding a no-op `@field_validator("date", mode="before")` makes the same call fail. `DateContent._reject_lax_temporal` (`pipelex/core/stuffs/date_content.py:46`) and `TimeContent._reject_lax_temporal` (`pipelex/core/stuffs/time_content.py:23`) are the only before-validators on non-JSON-native fields among the natives (`JSONContent`'s is on a `dict[str, Any]`, immune). `YesNoContent` has no before-validator and `bool` is a JSON type — hence the control passing.

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
- [ ] **`pipelex/core/stuffs/date_content.py`** — in `_reject_lax_temporal`, after the existing guards (datetime object, int/float/numeric-string epoch, datetime-shaped string on `date`), parse remaining `str` values: `datetime.date.fromisoformat` for `date`, `datetime.time.fromisoformat` for `time`. Wrap the `fromisoformat` `ValueError` in a clear message naming the field and the ISO 8601 expectation (must stay `ValueError` so pydantic wraps it into a `ValidationError`). Non-str values (real `date`/`time` objects, e.g. from `--mock-inputs`) pass through unchanged. Rename the validator (`_validate_temporal` or similar) — it no longer only rejects — and update its comment to state the second purpose: returning a real object is what keeps the model valid under the strict validation instructor applies to LLM responses (a before-validator forfeits pydantic's strict-JSON ISO-string acceptance).
- [ ] **`pipelex/core/stuffs/time_content.py`** — same change for `TimeContent.time`. Note: `fromisoformat` also closes the numeric-string hole (`"3600"`) that this class's guards never covered (DateContent guarded it, TimeContent didn't — flagged in the report as an asymmetry; decide whether to add the explicit epoch guard for the nicer message, mirroring DateContent).
- [ ] **Tests — red first** (`tests/unit/pipelex/core/stuffs/date_content/`, `.../time_content/`): a strict-mode module simulating the instructor path. Cases:
  - `DateContent.model_validate_json(..., strict=True)` with date-only and date+time payloads — the exact reported inputs (`"2025-03-12"`, `"14:00:00+00:00"`)
  - `TimeContent.model_validate_json(..., strict=True)` — offset preserved on `tzinfo` (fidelity), plus `Z` suffix and fractional seconds
  - strict **Python**-mode (`model_validate(..., strict=True)`) for both — instructor modes that validate parsed dicts
  - the generated list wrapper (the reported `ListOfDateContent` case): build it via `stuff_content_factory` list-class generation and validate a two-item payload under strict JSON
  - real `date`/`time` objects still accepted under strict (mock-inputs path)
  - all existing rejections still fire in **both** modes: `86400`, `"86400"`, `"8.64e4"`, `"20250312"` (epoch-lookalike, must NOT be parsed), `datetime` object, `"2026-07-07T00:00:00"` on `date`
  - malformed string (`"not-a-date"`) → `ValidationError` with the clear message
- [ ] Existing lax-path tests stay green (`test_date_content_serialization.py`, `test_time_content.py`, factory/input-shaper tests)
- [ ] `make agent-check`
- [ ] `make agent-test`
- [ ] **CHANGELOG.md** — `[Unreleased]`, bold-label style: `Date`/`Time` natives failed every live structured-output run (strict-mode validation of the LLM's ISO strings); now parse ISO 8601 in their validators so strict and lax paths agree.
- [ ] **Docs** — check `docs/` pages describing the `Date`/`Time` natives for anything stating the accepted forms; update if the parsing behavior is documented. No new page needed.

## Follow-ups (out of this repo, after release)

- [ ] `mthds-ui` (branch `feature/Native-concepts_stories`): `make fixtures-live ONLY=pipeline_32` to replace the placeholder LIVE fixture with real data — the natural end-to-end regression check named in the bug report. Gated on a released pipelex version carrying this fix.
- [ ] Optional live sanity check before release: run a gateway `PipeLLM` with `output = "Time"` / `Date[]` (the repro in the report) to confirm the production path.

## Cold-start pointers

- Failing call chain: `PipeLLM._run_operator_pipe` → `run_llm_object` (`pipelex/pipe_operators/llm/pipe_llm.py:284`) → worker `_gen_object` → instructor `create_with_completion(response_model=schema, ...)` → `function_calls.py` parse → `model_validate_json(..., strict=True)`.
- Gateway model config is fetched remotely (`pipelex/kit/configs/inference/backends/pipelex_gateway.toml` only allows `sdk`/`structure_method` overrides); the failing run used the openai-compatible gateway completions path, but the fix is mode-agnostic and provider-agnostic.
- Instructor pin: 1.15.1 (`.venv/lib/python3.13/site-packages/instructor/`).
