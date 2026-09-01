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

## Checkpoint — pre-landing review, two stamp defects found and fixed

Reviewing the branch with a real prettier (3.9.6, installed into the session scratchpad — it is not on this machine's PATH, so the skip-gated prettier test never runs here) turned up two ways the emitted `types.ts` was not prettier-stable. Both break the same thing: a consumer's formatter run changes the bytes and `pipelex codegen check` reports an untouched artifact as `[hand-edited]`.

**1. The `.nullable()` widening pushed ordinary defaulted fields past the print width, and only `z.enum` was modelled.** `_break_zod_expr`'s premise — "only `z.enum([...])` can genuinely overflow" — was already wrong and this change made it reachable on the commonest shape: the *field name* and the *default literal* are authored and unbounded, and neither is part of `expr`. Measured on one crate carrying a field named `default_summary_style` defaulting to `"a concise executive summary"`: 75 columns on this branch's merge-base and prettier-clean, 86 columns here and rewritten. `_render_field` detected the overflow and handed it to `_break_zod_expr`, which returned the identical flat string.

Probing prettier across every shape `_zod_type` can produce showed the real rule is simpler than the deferred declared-type case, and keys on **call count, not expression**: two or more calls in the chain and prettier breaks the whole chain (`z` alone on the property line, one call per line); a single call has no chain to break, so it explodes that call's arguments in place. `_break_zod_expr` now splits the expression into its member chain (`_split_member_chain`, on depth-zero dots — every literal in the emitted grammar sits inside a bracket) and renders that rule, keeping the enum-member explosion for a call still too wide after the break. The emission is now byte-identical to prettier's own output for the defaulted `z.string()`, `z.record(…)` + `.nullish()`, `z.number().int()` + `.nullish()`, `z.lazy(…)` + `.nullish()`, `z.array(…)` + `.nullish()`, bare enum, enum + `.nullish()`, and enum + `.nullable().default(…)`.

Two fields were added to `every_type_kind_crate` for it — a defaulted text field and a nested dict — so the **always-on** width guard carries the shape in CI where there is no node. Mutation-tested: restoring the enum-only break reddens `test_emitted_ts_lines_fit_the_print_width` naming both lines.

**2. A dict-valued default was rendered as JSON, which prettier rewrites at any width.** `_format_default_value` was `json.dumps(..., sort_keys=True)`, so a default emitted as `{"alpha": "first"}` while prettier writes `{ alpha: "first" }` — braces padded, and quotes dropped per key from every key that is a plain identifier (a key like `per-reviewer` keeps them). No line-width involvement at all: one dict default anywhere in a crate was enough. This is **pre-existing and independent of this campaign**, and `test_dict_defaults_are_canonical` was actively pinning the JSON bytes. Defaults now render through `_ts_literal` / `_ts_object_key`, the test pins the TypeScript spelling, and `every_type_kind_crate` gained a `quotas` default carrying both key spellings.

**3. An exploded choice list was split on every comma, in every target.** Re-reading the rewritten `_break_zod_expr` turned this up: the member split was `str.split(",")`, so a choice like `"blocked, awaiting the owner"` became two unterminated string literals. Not a formatting difference — the emission stops being TypeScript. The same defect sat in `python_common._split_top_level`, which explodes a `Literal[...]` annotation the same way, so both Python targets emitted unparseable Python on the same input; the Python half also has to walk *both* quote styles, because `escape_py_string` falls back to a single-quoted `repr` for a choice containing a `"`. Both splits now walk the string literals.

The Python half was already well guarded — reverting it reddens the ruff and line-length-stability tests loudly. The TypeScript half was guarded by **nothing**, and that is the lesson: the broken form is a run of *short* lines, so the print-width guard cannot see it, and no always-on test parses the emitted TypeScript (the prettier gate skips in CI and on this machine). `test_an_exploded_choice_keeps_its_own_commas` is the direct assertion that closes it, mutation-tested.

**4. A string carrying a `"` was always emitted double-quoted with escapes, and both formatters normalize it away.** `escape_py_string` deliberately converted repr's single-quoted form to double, and `json.dumps` always double-quotes; but ruff and prettier share one rule — double by default, single only where that **strictly reduces** the escape count — so `"marked \"urgent\""` is rewritten to `'marked "urgent"'` on the consumer's first format run, at any width, in all three targets. Probing ruff and prettier across the mixed, tied and backslash-adjacent cases pinned the rule exactly, and both emitters now implement it; every case round-trips back to the authored value, and the emission is byte-identical to what each formatter produces.

**The same blind spot appeared twice, and it is the thing to carry forward.** For defects 3 and 4 the Python half was caught loudly by the always-on ruff and line-length-stability guards, and the TypeScript half was caught by **nothing** — reverting either TS fix left the suite green. `test_emitted_ts_lines_fit_the_print_width` only measures *width*, and the prettier gate skips both in CI and on any machine without a node toolchain, which is every machine here. So the TypeScript target has no always-on guard on its *content*, only on its line lengths; each TS fix needed a direct byte assertion written for it. Worth a proper fix — a vendored TS parse, or making the prettier gate non-optional in CI — rather than another round of hand-written assertions. Filed as [L-260901-26da36](http://localhost:4747/i/L-260901-26da36).

### One defect found and deliberately deferred

The print-width guard exercises `_render_field` but never `_render_type_field`, because no fixture crate is recursive — so the whole declared-type path is unmeasured. Probing it turned up a real, reachable defect rather than a mere coverage hole: a recursive concept with an ordinary four-choice enum field emits a declared-type line at **118 characters**, prettier rewrites it to the leading-`|` broken form, and the resulting byte change makes `pipelex codegen check` report an untouched file as `[hand-edited]`.

It is **pre-existing and orthogonal to this campaign**: the same line measures 111 characters on this branch's parent commit, so the ` | null` widening makes the overflow easier to reach but does not cause it.

It is not a one-liner, which is why it was not folded in here. Probing prettier 3.9.6 across every shape `_ts_type` can produce: a literal union breaks in three tiers (flat, then break after the `?:`, then leading-`|` one per line); `Record<string, X> | null` and `Array<union> | null` explode the type-argument list; but `Array<atom> | null` and a bare long atom **stay flat past 80**. Those last two are the trap — prettier tolerates them, so the always-on width guard is *stricter* than prettier on this path, and simply adding a recursive fixture to it reddens shapes that are already prettier-clean. A correct fix models the union tiers and the type-argument explosion together, and teaches the guard the same distinction.

Filed as [L-260901-47759d](http://localhost:4747/i/L-260901-47759d) (owner `pipelex`), carrying the repro, the probe matrix and the parent-commit measurement.

## Checkpoint — review round 2, two splitter defects fixed and one deferred

Round 2 ran with no usable PR input: the branch's only review thread was already answered and resolved in round 1, and greptile has not re-reviewed since. The whole round came from the two reviewers run locally against `origin/dev` — cubic and Codex — which is exactly the case they exist for.

**Both fixed defects are the same mistake in two places, and both emit TypeScript that does not parse.** The round-1 fix introduced `_ts_string`, which spells a string single-quoted where that strictly reduces escapes; before it, every string went through `json.dumps` and was always double-quoted. Two new splitters were written in that same commit and neither was taught the new spelling.

1. **`_split_enum_members` walked only `"`.** Raised independently by cubic and Codex. A choice carrying both a `"` and a comma — `'say "hi", then continue'` — is spelled single-quoted and then cut at its own comma into two unterminated literals. *Not* a regression: the round-1 baseline split on every comma, so this input was broken there too. It was admitted under round 2's ship-blocker clause, because the consumer's build breaks rather than merely its stamp, and because the changelog already claimed the split walked the literals.

2. **`_split_member_chain` counted brackets inside literals.** Found in verification; neither bot named it, and it is the round's clean regression. Inside `z.enum([…])` the base depth is 2, so a choice list carrying two net-unmatched closers before a `.` walks the depth to zero mid-literal and cuts the member chain there. Plain enumerated prose does it: `["a) strongly agree with the proposal", "b) agree. with some reservations", "c unsure"]`. **The baseline emitter, on the identical input, emits valid TypeScript** — valid to invalid across round 1, since `_split_member_chain` is entirely new there.

Both now track the enclosing quote before counting anything, which is what `python_common._split_top_level` already did — the Python half was right all along and only the TypeScript half was left behind. Verified with prettier 3.9.6 installed into the session scratchpad: both shapes parse and are prettier-clean, and the skip-gated prettier test passes when run with it on PATH. Mutation-tested: reverting either splitter reddens its own byte assertion *and* the new class invariant.

**The blind spot got a cheap always-on guard at last.** `test_emitted_ts_never_breaks_a_line_inside_a_string_literal` scans each emitted code line and asserts none ends inside an unterminated literal. It needs no node toolchain, so it runs in CI, and it reddens on all three defects of this class rather than on the two that happened to be found — which is the point, since hand-written byte assertions have now missed this class three times. It is a stopgap, not the fix: a real parse or a non-optional prettier gate is still [L-260901-26da36](http://localhost:4747/i/L-260901-26da36). Note the guard skips comment lines deliberately — an authored description may hold an apostrophe, and the first draft failed on `/** The reviewer's answer */`.

### Deferred — `_ts_object_key` bypasses the quote rule

`_ts_object_key` renders a non-identifier object key with `json.dumps` rather than `_ts_string`, so a dict-default key carrying more `"` than `'` is emitted double-quoted with escapes and prettier rewrites it:

```
-     .default({ "marked \"urgent\"": 3 }),
+     .default({ 'marked "urgent"': 3 }),
```

Reachable — `default_value = { 'marked "urgent"' = 3 }` is legal TOML on a `type = "dict"` field — but narrow: `per-reviewer` and `it's` are both already spelled the way prettier wants. Raised by cubic; Codex reviewed the same diff and did not flag it.

**Deferred under the round-2 bar, deliberately.** It is a stamp instability only — the emission is valid TypeScript — and it is *not* a regression: the round-1 baseline rendered the whole dict as JSON and prettier rewrote both the brace padding and the quote, so round 1 made it strictly narrower and never worse. The fix looks like one word (`json.dumps(text)` → `_ts_string(text)`), which is precisely why it was left alone: the bar exists to stop a converging PR from taking on work that is neither a regression nor a blocker. It should be picked up in the follow-up that closes [L-260901-26da36](http://localhost:4747/i/L-260901-26da36), where a real TS parse would catch the whole family at once.

## Checkpoint — review round 3, one regression fixed

`/review` against `dev` with a real prettier (3.9.6, scratchpad install) found one defect and confirmed one known deferral.

**The chain break exploded an enum's members even when the enum fitted on its own line — a regression this branch introduces.** `_break_zod_expr`'s new member-chain path ran `_explode_enum_call` on any `.enum([…])` in the chain, unconditionally. Prettier does not: once the chain is broken it re-measures each call at its new indent and leaves flat any that fits, and the threshold is exact — probed member by member, `indent + len(call) <= 80` stays on the line, `81` explodes.

The shape that reaches it is ordinary, not contrived: `escalation_severity: z.enum(["low", "medium", "high"]).nullable().default("medium"),` is 86 columns flat, so it breaks; the `.enum([…])` is then 36 columns at indent 4 and prettier folds it straight back. **It is a regression rather than a pre-existing defect**, because `.nullable()` is what pushes the line over: the same field emits 75 columns on this branch's merge-base, stays flat, and is prettier-clean there. Verified both directions by emitting the same crate with the merge-base emitter.

`_render_broken_call` now applies the measurement, `every_type_kind_crate` carries the shape (`escalation_severity`, deliberately just inside the width where `fallback_state` is past it), and `test_a_broken_chain_keeps_a_call_that_fits_on_its_own_line` is the byte assertion. Mutation-tested: restoring the unconditional explode reddens it. The whole fixture emission is prettier-clean for real, and `test_emitted_ts_is_prettier_clean` passes with prettier on PATH rather than skipping.

**The deferred `_ts_object_key` case was re-confirmed and left deferred.** A dict-default key carrying more `"` than `'` is still emitted `{ "marked \"urgent\"": 3 }` and prettier rewrites it to `{ 'marked "urgent"': 3 }`. It remains a stamp instability on valid TypeScript, not a regression, and belongs with [L-260901-26da36](http://localhost:4747/i/L-260901-26da36).

## Checkpoint — review round 4, nothing found, and the round-3 fix verified against real prettier

This pass reviewed the code that landed *after* the previous agent-comment round — the `_render_broken_call` fix and the `origin/dev` merge — which no reviewer had seen. It changed no product code. (It is this branch's fourth review pass but carries the `round=3` stamp on the PR, because one earlier pass was run by `/review` rather than by the agent-comment skill, and only the latter stamps.)

**The PR's own threads contributed nothing again.** The single greptile thread was answered and resolved in round 1, and greptile's "Last reviewed commit" still names a commit several behind the branch head, so there has been no re-review. The whole round came from the two reviewers run locally against `origin/dev`.

**Codex reviewed the branch diff and found nothing.** cubic raised three, none of which clears the bar:

1. **The hand-rolled scanners are duplicated across `ts_zod.py` and `python_common.py`** and cubic would rather see the zod expression kept structural until final rendering. A design concern with no defect behind it, and the same concern already filed as [L-260901-26da36](http://localhost:4747/i/L-260901-26da36) — it belongs there, not in this PR.
2. **`sorted(pairs)` in `_ts_literal` crashes on a dict default with mixed key types.** Adjudicated as unreachable — the argument is below.
3. **`_ts_object_key` bypasses `_ts_string`.** The known deferral, re-raised for the third time; unchanged in status.

### `sorted(pairs)` — why the mixed-key crash is unreachable

Recorded in full because cubic is stateless and will raise it again, and a local-only finding has no PR thread to carry its adjudication.

cubic is right on the narrow point: nothing *validates* the key types. `default_value` is typed `Any | None` (`pipelex/core/concepts/concept_structure_blueprint.py:70`) and the `DICT` branch of `_validate_default_value_type` checks only `isinstance(self.default_value, dict)`. So `{1: "a", "b": 2}` would reach `sorted(pairs)` and raise `TypeError: '<' not supported between instances of 'str' and 'int'`.

It cannot get there. Both ingress formats guarantee string keys — a TOML table key is a bare or quoted key, a JSON object key is a string — and `clean_json_content` copies keys through verbatim without coercing them (`pipelex/tools/misc/json_utils.py`: `cleaned[key] = clean_json_content(content_dict[key])`, keys untouched). A dict whose keys are *uniformly* non-string sorts fine and is then handled by `_ts_object_key`; only the mixed case would crash, and no authored bundle can produce it.

Worth naming the inconsistency underneath, since it is what made the finding look reachable: `_ts_object_key`'s docstring says it stringifies a non-string key because "a crash here would be a worse answer than the spelling the emitter has always produced" — and `sorted()`, one line earlier, defeats that promise for the mixed case. That defence is pre-existing and is itself the over-engineering; extending it to satisfy the finding would add a second guard on a state neither guard can be reached in. Left alone deliberately.

### The round-3 fix now has empirical backing, not just a probe record

`_render_broken_call` rests entirely on a claim about prettier's behaviour, and on this machine `test_emitted_ts_is_prettier_clean` skips — prettier is not on PATH — so the claim had never been executed here. Installing prettier 3.9.6 into the session scratchpad and putting it on PATH makes the whole `tests/unit/pipelex/codegen/` suite run with **no skips**: the prettier gate and the node round-trip in `test_ts_zod_wire_agreement.py` both execute (node v24.17.0 and a global `zod` are present on this machine) and all pass.

**Mutation-tested against real prettier.** Restoring the unconditional explode reddens exactly two tests, and the second is the one that matters: `test_emitted_ts_is_prettier_clean` fails with prettier's own *"Code style issues found"* on the emitted `types.ts`, alongside the byte assertion `test_a_broken_chain_keeps_a_call_that_fits_on_its_own_line`. The fix is confirmed by the formatter it models, not only by an assertion written from a probe.

One more reading of the threshold, checked independently rather than taken from the commit message: `indent + len(call) <= TS_PRINT_WIDTH` is exact because the trailing comma never lands on an enum. `_zod_type` emits `.enum([…])` only for a top-level `LITERAL`; a nested one is wrapped, so its member call spells `.array(…)` or `.record(…)` and `_is_enum_call` does not match it. An enum is therefore always the *first* call in a broken chain and never the last one that carries the `,`, so the measured width is the rendered width.
