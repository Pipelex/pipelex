# CSV Support — Phase 2 code-review follow-ups (topics to revisit)

Status: **deferred — captured for a deliberate decision later, NOT a blocker for Phase 2.** Produced by an extra-high-recall `/code-review` of the Phase-2 codec implementation (`pipelex/tools/tabular/csv_codec.py`) on branch `feature/Support-csv` (worktree `_csv`).

This file holds review findings that are real but involve a **design tradeoff** rather than a rote fix — they shouldn't be patched reflexively. The mechanical/silent-correctness findings from the same review (blank-line phantom rows, over-wide-row truncation, delimiter/encoding boundary leak, write item-type guard, model-level coercion label) are tracked separately as the "fix-now" set in `TODOS.md`.

Line numbers are approximate anchors — grep the quoted token if they have drifted.

---

## #2 — Nullable-but-required column: mandatory vs. backfill-None (DEFERRED, PR #955 review round 6)

cubic flagged that a *nullable required* field (`x: str | None` with **no** default — pydantic reports `is_required() == True`) has a mandatory CSV column: omitting it raises `CsvColumnError` rather than backfilling `None`. cubic argues nullable columns should always be backfillable to `None`.

**Decision: keep current behavior (deferred, not adopted).** The rule "a column is mandatory ⟺ the field is pydantic-required" is intentional and *respects the author's signal*: writing `x: str | None` **without** `= None` is a deliberate "must be provided" choice (pydantic gives `X | None` no implicit default). Backfilling `None` would silently override that. The current code already maps an omitted *non-required* nullable column to `None` (round-4 `_annotation_allows_none`); only the *required* nullable case errors, which is correct. This is also unreachable from `.mthds`: a `required = false` field always compiles to `Optional[T] = None` (nullable WITH a None default → non-required → already `None` on omission), and a `required = true` field is non-nullable. So the distinction only arises for hand-built Python models. Revisit only if a real use-case wants "nullable ⟹ optional column" semantics.

---

## #1 — Non-string `Literal` / `Enum` row fields — RESOLVED (Option A, PR #955 review round 3)

**Resolution:** went with Option A (reject). `_is_flat_annotation` now accepts a `Literal` only when every arg is a `str`, and an `Enum` only when every member value is a `str`; a non-string `Literal`/`IntEnum` falls through to `CsvFlatnessError`. This keeps "flat ⇒ round-trippable" honest. Pinned by `IntLiteralRow`/`IntEnumRow` rejection cases + a `StrEnumRow` acceptance case. greptile + cubic both flagged it across rounds. The original tradeoff analysis is kept below for context.

---

### Original analysis (for context)

### Non-string `Literal` / `Enum` row fields: reject vs. coerce-on-read

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
