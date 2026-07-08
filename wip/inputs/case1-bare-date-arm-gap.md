# RESOLVED (Smart Inputs): a top-level array of date literals now builds `ListContent[DateContent]`

**Status:** **RESOLVED in Smart Inputs (2026-07-08, Phase-5 triage).** The signature-driven shaper closes the one real gap this note held (a top-level TOML date array). The historical framing is kept below for the record.

## What was flagged (Date-track PR review, 2026-07-07)

`StuffFactory.make_stuff_from_stuff_content_or_data` Case 1 (a value passed directly, not wrapped in a `{concept, content}` envelope) has arms for a bare `StuffContent` (1.3) and for `list[str]` / `list[StuffContent]` (1.2/1.4), but **no arm for a bare `datetime.date`/`datetime.datetime` object, nor for a `list[datetime.date]`**. The Date arm was only added to Case 2 (the envelope). So a bare date object or a date array reaching Case 1 falls through to an "unexpected type" / "Cannot create Stuff from list of ..." error.

## Bare scalar date → still DISMISSED (impossible on any real path)

A bare top-level `datetime.date`/`datetime.datetime` cannot reach Case 1:

- **CLI path:** the inputs-file loader's `_convert_temporal_inputs` (`_inputs_file_loader.py`) converts every **top-level** scalar date/datetime literal into a `DateContent` *before* the value reaches the seam. It therefore arrives as a `StuffContent` and is handled by Case 1.3 — never as a bare date.
- **API/protocol path:** the `StuffContentOrData` union (in mthds-python, `mthds/protocol/pipeline_inputs.py`) does **not** admit bare `datetime` objects. A well-typed caller cannot pass one.

Adding a bare-scalar-date arm to Case 1 would be a dead branch guarding a scenario no real caller produces. Not added.

## Top-level `list[datetime.date]` → RESOLVED by the shaper

The loader converts only top-level **scalar** temporal literals, so a top-level TOML array of date literals (e.g. `deadlines = [2026-01-01, 2026-02-02]`) is left as a `list[datetime.date]` and reaches the pipeline-inputs seam. With Smart Inputs live, that seam is `InputShaper.shape` (signature-driven), not the bottom-up factory: under a declared Date-refining `[]` input the list flows through `_shape_with_multiplicity` → `_shape_list` → the `InputKind.DATE` arm of `_build_item_content` (which accepts a `datetime.date`/`datetime.datetime` element and builds the declared `DateContent` subclass). The result is a `ListContent[DateContent]` typed with the declared concept — exactly what D2 + the shaper's Date arm promise. No Case-1.4 arm was added to the bottom-up factory; the fix is the top-down layer the note anticipated.

Pinned by `tests/unit/pipelex/core/memory/input_shaper/test_multiplicity.py::TestInputShaperMultiplicity` (the `variable-list-of-date-objects` case).

## Residual (unchanged, out of the shaper's scope)

The *no-signature* bottom-up path (`WorkingMemoryFactory.make_from_pipeline_inputs(..., input_specs=None)` → `StuffFactory` directly) still has no Case-1.4 date arm, so a `list[datetime.date]` reaching the factory without a signature still errors cleanly. That is correct: Smart Inputs shapes only when a signature is present, and the signature is what makes a date array interpretable. The broader protocol widening for sequences of scalars (design D10) rides the release wave regardless.
