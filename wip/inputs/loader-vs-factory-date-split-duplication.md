# Deferred: the date/datetime→DateContent split is written twice (loader + factory)

**Status:** deferred design note — no code change. Surfaced during the Phase 2 (Date inputs) code review, 2026-07-07.

## What

Two places turn a Python `datetime.date`/`datetime.datetime` object into a `DateContent`, with the same two-line split:

- `pipelex/cli/commands/run/_inputs_file_loader.py` → `_convert_temporal_inputs` (top-level TOML literals):

  ```python
  if isinstance(value, datetime.datetime):
      converted[key] = DateContent(date=value.date(), time=value.timetz())
  elif isinstance(value, datetime.date):
      converted[key] = DateContent(date=value)
  ```

- `pipelex/core/stuffs/stuff_content_factory.py` → `_make_date_content` (envelope / concept-resolved values):

  ```python
  if isinstance(value, datetime.datetime):
      return date_subclass(date=value.date(), time=value.timetz())
  if isinstance(value, datetime.date):
      return date_subclass(date=value)
  ```

The reviewer's suggestion was to have the loader call `StuffContentFactory.make_content_from_value(stuff_content_subclass=DateContent, value=value)` and delete its inline split.

## Why it is deferred (not applied)

It is a genuine design tradeoff, not a clear win:

- **Different layers, different responsibilities.** The loader is a *format-level* step (CLI, `pipelex/cli/…`) that maps a bare top-level TOML literal to the base `native.Date` content — it knows nothing about concepts. `_make_date_content` is a *concept-level* step that builds the concept's (possibly refining) `structure_class`. They happen to share a two-line split; they are not the same operation.
- **The reuse introduces a cross-layer dependency.** The loader currently imports only `DateContent`. Routing through `StuffContentFactory` couples the CLI loader to the core factory (and its `hub`/registry import surface) to save two lines of stable, trivial logic.
- **Low drift risk.** The split (`date=v.date(), time=v.timetz()` for a datetime; `date=v` for a date) is fixed by `datetime`'s own API; it is not the kind of logic that evolves.

## Follow-up to consider (Smart Inputs)

When Smart Inputs (D5/D10) unifies the bottom-up input paths into a shared `input_shaper`, the loader's top-level conversion and the factory's per-concept shaping likely collapse into one interpretation matrix. Resolve the duplication there — by unifying the layer, not by bolting a cross-layer call onto the current two hand-written arms.

No action needed inside the Date track.
