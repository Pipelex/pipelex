# Step F deferred notes

Deferred items surfaced while writing the Step F specs/conformance/docs. Same policy as the other deferred docs in this folder: none of these block phase 1; triage them with the cross-repo wave or on demand.

## Pre-existing: inline `$var` followed by ` (` escapes template variable detection

Found while ground-truthing the `optional_input_unguarded` conformance fixture. A prompt like `"Greet $name (nickname: $nickname)."` reports `extraneous_input_variable` for `name` — the inline `$name` reference is not detected as a variable use when it is immediately followed by a space and an opening parenthesis. `"Greet $name today, nickname: $nickname."` detects both fine. Most likely the preprocessed Jinja2 parses `name (…)` as a call expression, and the variable walker misses the callee (or the detection regex swallows the call shape). Pre-existing behavior, unrelated to optionals — reproduced with plain (non-optional) inputs too. Worth a small fix in the variable-detection walk (`jinja2` dissection utilities); the workaround is any other punctuation/wording between the variable and the parenthesis.

## Conformance optionals coverage is pinned ahead of the runtime — remove the gates at release

All new conformance coverage (the `CATEGORIZED_VALIDATION_ITEMS` rows, `tests/pipelex_api/test_validate_optionals.py`, `tests/pipelex_agent/test_validate_optionals.py`, and the QA-corpus cases) is gated on `OPTIONALS_PENDING_FEATURE` because the sibling venvs (`pipelex/.venv`, `pipelex-api/.venv`) run the released pipelex without optionals. Once a pipelex release with optionals ships **and** pipelex-api re-pins to it:

1. remove `pending_runtime_feature=OPTIONALS_PENDING_FEATURE` from the table rows and QA cases (the documented marker-removal policy),
2. run `make validate-error-qa` in `conformance/` to generate the committed artifacts for the six new cases,
3. drop the probe-skips if desired (they self-deactivate, but the gate comments say to remove them so regressions become visible).

## Absence records on the hosted wire — conformance pin awaits the mthds bump

The spec section "Absence records on run artifacts" is `<!-- unverified -->` by design: the hosted `/v1/execute` cannot return the `absences` ledger until the mthds SDK wire models can carry it (cross-repo hand-off item 1 in the tracker). When that lands, add an HTTP-arm conformance test (a PipeFunc/PipeCondition-only bundle whose optional output resolves absent) and flip the spec section to `> Verified by:`.
