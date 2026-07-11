# Deferred: temporal defaults inside a list/dict structure-field default aren't codegen-safe

**Status:** deferred design note — no code change. Surfaced during the Date-track PR #1029 adversarial review, 2026-07-07.

## What the reviewer flagged

DT8 taught `StructureGenerator._format_default_value` to render a **scalar** temporal default as `date.fromisoformat("…")` / `datetime.fromisoformat("…")` — because `repr()` module-qualifies a temporal object (`datetime.date(2026, 7, 7)`), and the generated code imports the *bare* classes (`from datetime import date, datetime`) with `exec_globals` binding `datetime` to the datetime *class*. Under those globals, `datetime.date(2026, 7, 7)` resolves to the `datetime.date` method descriptor and raises `TypeError` at exec.

The scalar fix does not recurse into containers. A `date`/`datetime` object nested inside a **list or dict default** falls through to the `repr()` branch, so the same module-qualified form is emitted and the generated class body raises at exec.

## Reachability — real but narrow

Confirmed reachable through a hand-written `.mthds` concept structure field:

- The core `ConceptStructureBlueprint._validate_default_value_type` LIST arm only checks `isinstance(self.default_value, list)` — it does **not** validate element types. So `{type = "list", item_type = "date", default = [2026-07-07]}` passes blueprint validation. (The spec layer forbids list/dict defaults, but the blueprint layer — the one the generator consumes — does not.)
- The list default then reaches `_format_default_value([date(2026, 7, 7)])`, which is neither `str` nor a scalar `date`/`datetime`, so it hits `repr(...)` → `"[datetime.date(2026, 7, 7)]"` → cryptic `TypeError` (`descriptor 'date' for 'datetime.datetime' objects doesn't apply to a 'int' object`) at concept-build time, on otherwise-valid MTHDS input.

## Why deferred, not fixed in the Date track

- **Not a regression.** The container `repr()`-qualification bug pre-dates DT8: before DT8, a `type = "date"` scalar *and* a list-of-date default both hit `repr()` and broke. DT8 fixed the scalar case; the container case was already broken and stays broken.
- **Errors, does not silently corrupt.** It fails loudly at concept build, so no wrong data ships.
- **The fix is a design choice, not a mechanical patch.** Two reasonable shapes: (a) make `_format_default_value` recurse into list/dict/tuple and emit `fromisoformat(...)` per temporal element; or (b) reject container defaults containing temporal objects at blueprint validation with a clear message (turning the cryptic exec error into a proper `default_value type mismatch`). (b) is smaller and arguably the better guard; (a) is more complete. Deciding belongs with whoever revisits structure-field defaults, not bolted onto the Date track.

## Follow-up to consider

When structure-field default handling is next touched (Smart Inputs, or a dedicated codegen pass), pick (a) or (b) above. If (a), share the temporal-formatting helper the scalar branch already uses. Related notes: `case1-bare-date-arm-gap.md`, `loader-vs-factory-date-split-duplication.md`, `structure-field-fidelity-guard.md`.

No action needed inside the Date track.
