# CSV Support — Phase 2 code-review follow-ups (topics to revisit)

Status: **deferred — captured for a deliberate decision later, NOT a blocker for Phase 2.** Produced by an extra-high-recall `/code-review` of the Phase-2 codec implementation (`pipelex/tools/tabular/csv_codec.py`) on branch `feature/Support-csv` (worktree `_csv`).

This file holds review findings that are real but involve a **design tradeoff** rather than a rote fix — they shouldn't be patched reflexively. The mechanical/silent-correctness findings from the same review (blank-line phantom rows, over-wide-row truncation, delimiter/encoding boundary leak, write item-type guard, model-level coercion label) are tracked separately as the "fix-now" set in `TODOS.md`.

Line numbers are approximate anchors — grep the quoted token if they have drifted.

---

## #1 — Non-string `Literal` / `Enum` row fields: reject vs. coerce-on-read

**The finding.** The flatness gate `_is_flat_annotation` (`pipelex/tools/tabular/csv_codec.py:67`, `if origin is Literal: return True`; `:70`, `issubclass(annotation, Enum) → True`) accepts *any* `Literal` and *any* `Enum` as CSV-flat. But the codec can only round-trip **string-valued** ones:

- `_to_cell` writes the value as a bare string (`1`) or lowercased bool (`true`).
- On read, pydantic's `Literal`/`Enum` validator does **not** coerce that string back to the typed member.

Verified: `Literal[1,2,3]` writes `1` → read raises `CsvCoercionError`; `Literal[True,False]` writes `true` → fails; an `IntEnum` likewise. `Literal["low","high"]` (and `StrEnum` / str-valued `Enum`) round-trip fine. So a concept the gate declares "flat" can silently fail its own round-trip.

**Why it's deferred (the tradeoff).** Non-string `Literal`/`Enum` fields are **not reachable from `.mthds` today**, so this is not a live data-corruption risk:

- The structure generator *always* emits **string** `Literal`s — even integer/number "choices" compile to `Literal['1','2',…]`: `pipelex/core/concepts/structure_generation/generator.py:318-320` (`python_type = f"Literal[{', '.join(repr(c) for c in field_blueprint.choices)}]"`, fed by string choices).
- `choices` is validated as `list[str]`: `pipelex/core/concepts/concept_structure_blueprint.py:60` (`choices: list[str] | None`), and is only allowed on text/integer/number types: `pipelex/builder/concept/concept_spec.py:150-162`.
- The generator never produces `Enum`/`StrEnum` subclasses at all.

So non-string `Literal`/`Enum` only arise from hand-built `StructuredContent` subclasses (e.g. tests). Two ways to resolve, with different futures:

- **Option A — reject (simple, safe now).** Tighten the gate to accept only string-valued `Literal` (`all(isinstance(arg, str) for arg in get_args(...))`) and str-valued `Enum` (`all(isinstance(m.value, str) for m in enum)`); non-string members fall through to the existing `CsvFlatnessError`. Breaks no reachable concept, keeps "flat ⇒ round-trippable" honest. **Downside:** forecloses (or makes the codec inconsistent with) a future where integer/number choices materialize as real `Literal[int]` / `IntEnum` and someone wants them in CSV.
- **Option B — coerce-on-read (preserves future support).** For a `Literal`/`Enum` field, coerce the cell string against the member's underlying scalar type (or match by `str(member)`/`member.value`) before/within validation, so `1` → `Literal[1,2,3]` works. More code; partly duplicates pydantic; needs care for mixed-type literals.

**Recommended default if forced to pick now:** Option A (reject) — it's the smallest correct change and matches the current `.mthds` reality. Revisit toward Option B **only if** the structure generator ever emits typed (non-string) `Literal`/`Enum` for choices, at which point CSV support for them should be a deliberate feature with its own coercion + round-trip tests.

**Decision owner:** revisit when (a) touching the choices/structure-generation typing, or (b) a user asks for integer/enum-typed CSV columns. Until then this is a latent gap behind an unreachable code path, intentionally left as-is.
