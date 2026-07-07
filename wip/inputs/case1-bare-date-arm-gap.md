# Deferred: StuffFactory Case 1 has no bare-date arm (and Case 1.4 no `list[datetime.date]`)

**Status:** deferred design note — no code change. Surfaced during the Date-track PR review, 2026-07-07.

## What the reviewers flagged

`StuffFactory.make_stuff_from_stuff_content_or_data` Case 1 (a value passed directly, not wrapped in a `{concept, content}` envelope) has arms for a bare `StuffContent` (1.3) and for `list[str]` / `list[StuffContent]` (1.2/1.4), but **no arm for a bare `datetime.date`/`datetime.datetime` object, nor for a `list[datetime.date]`**. The Date arm was only added to Case 2 (the envelope). So a bare date object or a date array reaching Case 1 falls through to an "unexpected type" / "Cannot create Stuff from list of ..." error.

## Bare scalar date → DISMISSED (impossible on any real path)

A bare top-level `datetime.date`/`datetime.datetime` cannot reach Case 1:

- **CLI path:** the inputs-file loader's `_convert_temporal_inputs` (`_inputs_file_loader.py`) converts every **top-level** scalar date/datetime literal into a `DateContent` *before* the value reaches the seam. It therefore arrives as a `StuffContent` and is handled by Case 1.3 — never as a bare date.
- **API/protocol path:** the `StuffContentOrData` union (in mthds-python, `mthds/protocol/pipeline_inputs.py`) is `str | Sequence[str] | StuffContentAbstract | Sequence[StuffContentAbstract] | dict[str, Any]` — it does **not** admit bare `datetime` objects. A well-typed caller cannot pass one.

Adding a bare-scalar-date arm to Case 1 would be a dead branch guarding a scenario no real caller produces. Not added.

## Top-level `list[datetime.date]` → deferred (clean error, not a silent bug)

There is one real-but-minor gap: the loader only converts top-level **scalar** temporal literals, not lists. A top-level TOML array of date literals (e.g. `deadlines = [2026-01-01, 2026-02-02]`) is left as a `list[datetime.date]`, reaches Case 1.4, and errors (no matching arm) instead of building a `ListContent[DateContent]`.

This is deferred rather than fixed because:

- It **errors cleanly** (raises `StuffFactoryError`), it does not silently corrupt data.
- List/sequence inputs of natives are **not** part of the Date track's promised surface — the docs advertise top-level scalar date/datetime literals only. Protocol widening for sequences of scalars rides Smart Inputs (design D10).
- A local patch here would be **half-baked and asymmetric**: the scalar path converts to `DateContent` early (in the loader), so bolting a late list-conversion arm onto the factory would deepen exactly the loader-vs-factory split already captured in `loader-vs-factory-date-split-duplication.md`.

## Follow-up to consider (Smart Inputs)

When Smart Inputs (D5/D10) unifies the bottom-up input paths into a shared `input_shaper` and widens the protocol to sequences of scalars, decide there how a top-level array of date literals should map to `ListContent[DateContent]` — by unifying the layer, not by hand-adding one more Case 1.4 arm. Related notes: `scalar-envelope-arm-asymmetry.md` (Case 2 bool-vs-str), `loader-vs-factory-date-split-duplication.md` (where the split lives).

No action needed inside the Date track.
