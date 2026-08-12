# `Date` and `Time` cannot be produced by a live `PipeLLM`

## The bug

A `PipeLLM` whose `output` is `Date`, `Date[]`, or `Time` fails every live run with a pydantic validation error. The natives are authorable, validate, and dry-run clean — they only break when a real model answers.

Reproduced on pipelex **0.42.0**, gateway backend, `claude-4.6-sonnet`, deterministic across repeats:

```
Error generating single object with direct method in pipe 'read_one_time':
openai inference failed for model 'claude-4.6-sonnet → ...': 1 validation error for TimeContent
time
  Input should be a valid time [type=time_type, input_value='14:00:00+00:00', input_type=str]
```

```
Error generating list of objects with direct method in pipe 'read_dates':
... 2 validation errors for ListOfDateContent
items.0.date
  Input should be a valid date [type=date_type, input_value='2025-03-12', input_type=str]
items.1.date
  Input should be a valid date [type=date_type, input_value='2025-03-14', input_type=str]
```

A single `Date` fails on **both** its fields (`date` and the optional `time`) in one response.

## Scope

| Native output | Live run |
| ------------- | -------- |
| `YesNo`       | works    |
| `Date`        | fails    |
| `Date[]`      | fails    |
| `Time`        | fails    |

`YesNo` is the control: same bundle shape, same model, same path, succeeds. So this is specific to the temporal contents, not to the recently-added natives as a group.

## Why it looks unintended

The model the LLM returns is JSON. A JSON document has no date or time type, so a `datetime.date` field can only ever arrive as a **string** — `"2025-03-12"` is the correct and only possible representation. Rejecting it makes the concept unusable in the one position authors most want it: an LLM reading a date out of text.

`TimeContent._reject_lax_temporal` (`pipelex/core/stuffs/time_content.py:23`) is written to allow exactly that. It rejects numbers (guarding pydantic's seconds-since-midnight coercion) and `datetime` objects, then **returns the value unchanged** — an ISO string is meant to pass and be coerced. `DateContent` carries the same shape, and both fields' `Field(description=...)` explicitly tell the model to answer "in ISO 8601 (e.g. 2026-07-07)".

The `YesNo` control makes this sharper. `YesNoContent.yes_no` declares `strict=True` **explicitly, on the field**, with a comment explaining why — and it survives a live run, because `bool` is a JSON type so a strict bool is satisfiable. `DateContent.date`, `DateContent.time`, and `TimeContent.time` declare no strictness at all, yet fail with strict-mode errors. So in this codebase strictness is opt-in per field where it is meant, and these three fields did not opt in.

The error code is the tell. Pydantic emits `time_parsing` / `date_parsing` when a _lax_-mode coercion fails on a malformed string, and `time_type` / `date_type` when _strict_ mode refuses a string outright. We get `time_type` / `date_type` on well-formed ISO input — so the structured-output path is validating these models in **strict mode**, which bypasses the coercion `_reject_lax_temporal` was written around. The validator's intent and the validation mode disagree.

## Where to look

The failing call is the `direct` structured-output method through the openai-compatible gateway completions path (`ListOfDateContent` is the generated list wrapper). Whatever constructs or validates the response model there is applying strict validation; `StuffContent` itself declares no `model_config`, so the strictness is coming from the inference/structured-output layer rather than the content models.

**The inputs path is fine — checked.** A `Date` supplied through `inputs.json` as `{"date": "2025-03-12"}` validates and runs green, even though it presents the identical JSON string to the identical field. So the two paths disagree: the same value pipelex happily accepts from an author it refuses from a model. That narrows the fault to the structured-output/inference layer and rules out the content models themselves.

## Impact

`Date` and `Time` are pinned MTHDS natives — part of the standard's vocabulary — that currently cannot be produced by the primary operator. Any author who types `output = "Date"` gets a method that validates, dry-runs green, and then fails in production on the first real call. The dry-run/live gap is the worst part: `--mock-inputs` fabricates real `datetime` objects, so nothing upstream of a paid run reveals it.

## Downstream note

Filed from `mthds-ui` while adding native-concept fixture coverage (`data/pipelines/pipeline_32`, branch `feature/Native-concepts_stories`). That bundle is committed with its honest authored shape — `Date[]` and `Time` as `PipeLLM` outputs — and a **placeholder** LIVE fixture, because pipelex cannot produce a real one. When this is fixed, `make fixtures-live ONLY=pipeline_32` in `mthds-ui` replaces the placeholder with real data and is the natural regression check.
