---
status: active
item: L-260820-ee327d
---

# ts-zod projection: accept the wire's explicit nulls

Ledger item: L-260820-ee327d. Branch: `fix/Zod-codegen` (worktree `_zod`).

## The problem

The ts-zod emitter projects a non-required concept field as `.optional()`, which in zod means `T | undefined` and rejects `null`. The runtime serializes an unset optional field as an explicit `null`: the generated runtime class annotates every non-required field `X | None` (`pipelex/core/concepts/structure_generation/generator.py`, `_generate_field_line`), and the transport dump keeps nulls deliberately — `dump_for_transport()` is `model_dump(serialize_as_any=True)` with no `exclude_none` (`pipelex/core/memory/working_memory.py`), and the composer even spells `exclude_none=False` at every dump site (`pipelex/pipe_operators/compose/structured_content_composer.py`). So the generated `Schema.parse` rejects the very payload the runtime produces — live evidence in the ledger item: a successful hosted `PipeImgGen` run fails `ImageSchema.parse` with one issue per nulled optional.

## Decision: fix the projection, not the wire

Emit a null-tolerant zod modifier for non-required fields. The alternative — dumping the transport payload with `exclude_none=True` so absent means absent — is rejected:

- The runtime keeps nulls **on purpose**: `exclude_none=False` is written out explicitly at the composer's dump sites. The transport dict also feeds the Temporal data converter and the hydrator; changing its shape is a wire redesign with its own review, not a codegen bug fix.
- The Python projections already accept both spellings — `python-pydantic` and `python-structures` both render non-required fields as `X | None = Field(default=None)`. ts-zod is the one projection that disagrees with the runtime; this is a parity fix.
- The wire genuinely carries both spellings of "unset" (a key omitted by a partial payload versus a key the runtime nulled). A projection should describe the wire honestly, and `.nullish()` is exactly that description. No `.transform()` to fold `null` into `undefined`: the binder uses one schema for both `parse` and `serialize`, and a transform would make them asymmetric.

Consumer cost: parsed values are `T | null | undefined` instead of `T | undefined`; `??` covers both.

## Phase 1 — emitter change

All in `pipelex/codegen/emitters/ts_zod.py`:

- `_render_field`: non-required without default → `.nullish()` (today `.optional()`); non-required **with** default → `.nullable().default(...)` (today `.default(...)` alone, which rejects null even though the runtime type is `X | None = Field(default=…)` and a producer can set it to `None` explicitly). The blueprint validator rejects `required = true` beside a default (E3), so every defaulted field is non-required — the `.default(...)` branch always needs `.nullable()`.
- `_render_type_field` (the explicit-type path for recursive concepts): widen every non-required field's type with `| null`; keep the `?` marker only for the no-default case, as today. The declared type must match the schema's inferred output (`.nullish()` → `field?: T | null`; `.nullable().default(…)` → `field: T | null`) or the `z.ZodType<Name>` annotation stops typechecking.
- Prettier-width modeling: `.nullish()` is shorter than `.optional()` — no risk there — but `.nullable().default(...)` adds width to a branch `_break_zod_expr` only models for `z.enum`. Extend the crate fixtures (Phase 2) so the width guard exercises the new form; if `test_emitted_ts_lines_fit_the_print_width` or the prettier-clean test reds, extend `_break_zod_expr` to model prettier's member-chain break for the overflowing shape rather than loosening the guard.

`.nullish()` and `.nullable()` exist in both zod 3 and zod 4, so the emitted `import { z } from "zod"` contract is unchanged.

## Phase 2 — tests

- Update `tests/unit/pipelex/codegen/test_ts_zod_emitter.py`: the `.optional()` assertions become `.nullish()`; the defaulted assertions (`status`, `starts_on`, `recorded_at`) gain `.nullable()`. Add explicit coverage for both modifier branches and for the recursive-concept explicit-type path carrying `| null`.
- Make sure the `every_type_kind_crate` fixture carries a non-required defaulted field, so the always-on width/whitespace guards and the local prettier-clean test exercise `.nullable().default(...)`.
- New module `tests/unit/pipelex/codegen/test_ts_zod_wire_agreement.py` — the round-trip check the ledger item asks for, in three layers on one shared crate (non-required fields with and without defaults, nested concept, list/dict types):
  1. **Wire pin (always on, pure Python).** Build the runtime class the way the runtime does (`ConceptFactory` / the structure generator, as `test_projection_agrees_with_runtime_base.py` already does), instantiate it with the optionals unset, dump via the transport idiom (`model_dump(serialize_as_any=True)`), and assert the unset keys are present with `None`. This pins the wire truth the projection must accept; if the transport dump ever flips to `exclude_none`, this test reds and forces the projection decision to be revisited together with it.
  2. **Projection pin (always on).** Emit ts-zod for the same crate and assert every non-required field's expression is null-tolerant. Paired with (1), the cross-language contract is encoded in this repo even where CI has no node.
  3. **Executable round-trip (local-only, skip-gated like `test_emitted_ts_is_prettier_clean`).** When `node` (≥ 22.6, for `--experimental-strip-types`) and a globally installed `zod` (`npm root -g`) are available: write the emitted `types.ts` plus a tiny driver into a tmp dir, symlink the global `zod` into a local `node_modules`, feed the JSON from (1) through `Schema.parse`, and assert success and that nulls survive as nulls. Skip otherwise — the always-on pins hold the line in CI.

## Phase 3 — docs and changelog

- `docs/under-the-hood/codegen-projections.md`: state the optionality contract in one place — the runtime serializes unset optionals as explicit `null`, every projection must accept both spellings, and per target that means `X | None` (Python) and `.nullish()` / `.nullable().default(…)` with `| null` types (ts-zod).
- `CHANGELOG.md` under `## [Unreleased]`: breaking for generated TypeScript artifacts — regenerate; parsed optional fields now type as `T | null | undefined`.

## Phase 4 — landing and follow-through

- Run `make agent-check` and `make agent-test`; PR against `dev` with `Closes L-260820-ee327d` in the body.
- File the consumer cleanup now, blocked on this item: a `pipelex-starter-js`-owned item to delete `src/lib/wireOutput.ts` (`dropWireNulls`) and regenerate `src/generated/` once a pipelex release carrying this fix is deployed to the hosted codegen route. The workaround silently strips legitimate nulls inside opaque fields, so it should not outlive the fix.
- Note for L-260830-344594 (pipelex-integrate skill): its plan carries a pre-ship re-check of this item — once this ships in the hosted engine, the skill never writes the wireOutput helper into user projects. Drop a `ledger note` on that item when this merges.

The fix reaches consumers only through a pipelex release plus an api-dev deploy (the starter consumes the projection via hosted `POST /v1/codegen`); the release itself rides the normal release train and is not scheduled by this plan.

## Checkpoint — Phases 1–3 done, green locally

**`_break_zod_expr` did need extending, and the reason is prettier's member-chain rule, not width.** The modifier was a single string; `.nullable().default(…)` is two member calls, and once prettier breaks a member chain it puts *every* call on its own line — so the emitted overflow form had to become `z\n    .enum([…])\n    .nullable()\n    .default("…")`. The fix is to carry the presence modifiers as a **list** end to end: `_presence_modifiers(concept_field)` returns the chain, `_render_field` joins it flat, and `_break_zod_expr` renders one member per line. Nothing else about the break logic changed — `z.enum([...])` is still the only expression that can genuinely overflow.

Verified for real rather than reasoned about, with prettier and typescript installed into the session scratchpad (neither is on this machine's PATH, so both skip-gated tests skip in an ordinary run):

- `prettier --check` is clean on the `every_type_kind_crate` emission carrying the new `fallback_state` field — the exact multi-member chain break above.
- `tsc --strict` is clean on a recursive crate whose `Node` carries a nullish concept ref, a nullish list, a nullish enum, a nullish record, a defaulted text field and a required int. Dropping ` | null` from one declared type reproduces the failure the widening exists to prevent: *`Node | null | undefined` is not assignable to `Node | undefined`* on the `z.ZodType<Node>` annotation. The widening is load-bearing, not cosmetic.

**The node round-trip gate keys on two things**, both probed at test time: `node --version` parsed and compared against 22.6 (`--experimental-strip-types`, which is what lets node run the emitted `.ts` directly), and a `zod` package with a readable `package.json` under `npm root -g`, symlinked into a tmp `node_modules`. A tmp `package.json` carrying `{"type": "module"}` silences node's typeless-package reparse warning. Anything missing skips; the two always-on pins carry CI. Note this session ran `npm install -g zod` to make the gate open locally — a machine without it simply skips.

**The wire pin needed one thing the plan did not anticipate.** A concept reference is generated as a *quoted forward ref*, so instantiating the runtime class raises `PydanticUserError: not fully defined` until the classes are rebuilt against a shared namespace. The fixture mirrors what the library manager does on load (`_rebuild_models_with_forward_refs`) rather than working around it, which keeps the pin faithful to the runtime path.

**Mutation-tested.** Reverting `_presence_modifiers` to `.optional()` / bare `.default(…)` reddens both the projection pin and the executable round-trip, the latter with zod's own *"expected record, received null"* on the runtime's own payload — the ledger item's failure, reproduced in this repo.

One coverage gap left open deliberately: the print-width guard exercises `_render_field`, not `_render_type_field`, because no fixture crate is recursive. A long enough concept name plus ` | null` could overflow a declared-type line; `test_emitted_ts_lines_fit_the_print_width` would catch it only once a recursive crate reaches that fixture.
