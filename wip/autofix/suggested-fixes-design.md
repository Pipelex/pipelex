# Suggested fixes on validation diagnostics

Design for deterministic auto-fixing of `.mthds` bundles. Supersedes [old-plan-to-auto-fix.md](old-plan-to-auto-fix.md) (the `feature/Bundle-fixer` approach).

## Decisions taken (2026-07-07, with Louis)

- **D1 — Fixes attach to diagnostics.** Each fixable `ValidationErrorItem` carries a structured `suggested_fix`. The `fix` command is just "apply what validate found", in a loop. No standalone fix engine that re-derives problems.
- **D2 — Runtime-only wire first.** `suggested_fix` is an additive, optional, pipelex-owned field. Formal promotion into the MTHDS protocol (spec + conformance + downstream schema copies in mthds / mthds-js / mthds-python) is a later wave, once the shape is proven.
- **D3 — Wave 1 consumer = agent CLI + skills.** `pipelex-agent fix` with the convergence loop, consumed by the `mthds-fix` skill and hooks. API `POST /fix`, MCP `mthds_fix` tool, and VS Code quick fixes are later waves.
- **D4 — Pruning rules cut from wave 1.** `prune-unreachable` / `prune-unused-concepts` are cleanups, not fixes — nothing is broken when they'd fire. Salvage the graph-walk logic later as opt-in lint warnings with attached fixes. Wave 1 is purely "make invalid bundles valid".

## Why this shape (and why not the old branch's)

The old branch built a separate fix engine that re-implemented the validation pipeline (`_load_blueprint_and_pipes` hand-copied `validate_bundle`'s phases) and re-derived the correct values on its own. Two engines computing the same truths is a drift machine, and a fix computed inside a command is invisible to every other consumer (API, MCP, VS Code, skills).

The decisive observation: **the validator already knows the correct value at detection time.** `PipeSequence.validate_output_with_library` (`pipelex/pipe_controllers/sequence/pipe_sequence.py:63-115`) compares the declared output against the last step's output and already ships the correct concept in the error (`provided_concept_code`). `generic_validate_inputs_with_library` (`pipelex/core/pipes/pipe_abstract.py:264`) compares declared inputs against `needed_inputs()`. So fixability comes from **richer typed errors**, not from a smarter fixer: enrich the error to carry the expected value, and fix construction becomes a mechanical translation that cannot drift from the validator.

This also matches the workspace's presentation-vs-contract principle (`docs/specs/pipelex-mthds-protocol.md`): the fix ops are contract data on the structured report; any rendered diff is presentation. One validation engine keeps feeding every surface.

## Architecture

Three layers, all in `pipelex/`:

1. **Enriched typed errors** (validator sites). Where a validator computes the expected value, it puts that value on the typed error as structured fields (e.g. the expected output ref including multiplicity, the full needed-inputs mapping). Validators gain no TOML knowledge — they state semantic facts. This is valuable even without autofix: it makes error messages and agent-facing explanations better.
2. **Fix planner** (one module, e.g. `pipelex/pipeline/fixes/`). Translates enriched typed errors into `SuggestedFix` payloads: semantic patch ops addressed by TOML path. Keyed strictly off `error_type` + structured fields — never message strings. The planner runs inside report assembly (`build_validation_error_items` / `build_validation_report`), so every consumer of the report sees fixes with zero extra plumbing.
3. **Applier + loop** (tomlkit-based). Applies ops to the raw file's tomlkit DOM (style-preserving), per file. The `fix` command loops: validate → collect safe fixes → apply → re-validate, until fixed-point.

### Wire model (wave 1, runtime-only per D2)

```python
class FixOpKind(StrEnum):
    SET_KEY = "set_key"          # set (or create) a key's value at a table path
    DELETE_KEY = "delete_key"
    DELETE_TABLE = "delete_table"
    RENAME_TABLE_KEY = "rename_table_key"   # position-preserving; needed for strip-namespace (stretch)

class FixOp(BaseModel):
    kind: FixOpKind
    table_path: list[str]        # e.g. ["pipe", "my_seq"] — aligned with field_path conventions
    key: str | None
    value: TomlValue | None      # TOML-representable
    new_key: str | None          # rename only

class SuggestedFix(BaseModel):
    fix_code: str                # kebab-case rule id, e.g. "match-sequence-output"
    description: str             # human/agent-readable, e.g. "Set output to 'Report[]' to match last step"
    safety: FixSafety            # SAFE (auto-appliable) | UNSAFE (opt-in)
    source: str | None           # file the ops target (multi-file libraries)
    ops: list[FixOp]
```

`ValidationErrorItem` gains `suggested_fix: SuggestedFix | None = None`. Serialization stays `exclude_none`, so nothing changes for non-fixable errors. Naming is brand-neutral (language-level concept — no `pipelex_` prefixes in field names).

Note `ValidationErrorItem` flows through the hosted API's `InvalidReport` too, so the field will *appear* on the API wire as soon as it exists — that's fine and additive; what D2 defers is the formal contract work (spec sections, conformance tests, downstream schema mirrors), not hiding the field.

### The applier

- tomlkit DOM per file (`load_toml_with_tomlkit` / `save_toml_to_path` in `pipelex/tools/misc/toml_utils.py` already exist). Comments, ordering, and table style of untouched content survive by construction.
- **In-place mutation, never rebuild.** For `sync-controller-inputs`, update/delete/add keys inside the existing `inputs` table rather than replacing it with a fresh inline table (the old branch's rebuild discarded comments and forced inline style).
- **Position-preserving rename** for `RENAME_TABLE_KEY` (the old branch's `del` + re-add sent renamed pipes to the bottom of `[pipe]`). If tomlkit makes this too fiddly, `strip-namespace` stays out of wave 1 rather than shipping the reordering bug.
- **Guarded application**: an op only applies if its target path exists in the DOM. This protects against errors raised on elaborated/synthetic constructs (`BundleElaborator` synthesizes sequences from `structuring_method = "preliminary_text"` — those pipes have no TOML to patch) and against ops targeting a different file than the one being patched.
- **Idempotent**: applying the same fix twice is a no-op.

### The convergence loop (`fix` command)

```
loop (max_iterations, default 5):
    report = validate_bundle(...)            # THE validator — no parallel pipeline
    fixes  = [e.suggested_fix for e in errors if fix is SAFE and selected]
    if no fixes: break
    if fingerprint(fixes) seen before: break  # no-progress bail, report loudly
    apply fixes per file; write
final: re-validate, report is_valid + fixes_applied + remaining errors
```

Cascades are expected (fixing a sequence's output can surface a downstream input mismatch) — the loop is the design, not a fallback. The old branch's "fixes are convergent in a single pass" was asserted, never proven; here non-convergence is a first-class, loudly-reported outcome, and the loop-with-fingerprint makes it impossible to spin.

## Wave 1 fix rules

| fix_code | Trigger (typed) | Fix | Safety |
| --- | --- | --- | --- |
| `match-sequence-output` | `INADEQUATE_OUTPUT_CONCEPT` / `INADEQUATE_OUTPUT_MULTIPLICITY` on a **PipeSequence** | `set_key` the sequence's `output` to the last step's effective output (concept + multiplicity, honoring the sub-pipe multiplicity override) | SAFE |
| `sync-controller-inputs` | `MISSING_INPUT_VARIABLE` / `EXTRANEOUS_INPUT_VARIABLE` / `INPUT_STUFF_SPEC_MISMATCH` on a **controller** pipe | In-place sync of the `inputs` table with `needed_inputs()` | SAFE |
| `strip-native-concept-redecl` | Blueprint validation error for redeclared native concept | `delete_table` / `delete_key` for `[concept.X]` or inline `concept.X = "..."` | SAFE |
| `strip-namespace` (stretch) | `INVALID_PIPE_CODE_SYNTAX` from same-domain dotted pipe codes | Position-preserving rename + rewrite of internal refs (`steps`, `branches`, `branch_pipe_code`, `outcomes`, `default_outcome`, `main_pipe`) | SAFE, but gated on rename mechanics |

Explicitly **not** fixable (ambiguous, requires judgment): PipeParallel/PipeCondition output choice, `INPUT_STUFF_SPEC_MISMATCH` on operator pipes, generating missing concepts, anything on signature pipes (signatures are `pending_signatures`, never errors — the fixer must never touch them). The old branch's `fix-list-notation` is dropped: it fired unconditionally rather than off errors, only ever added `[]`, and predates the optionals grammar; if the underlying case matters it should resurface as a properly error-driven rule.

### Rule-level guards (lessons from the drift analysis)

- **Optionals markers `?` / `!`**: any rewrite of an input/output ref must preserve the author's presence markers. The validator deliberately does not compare presence markers in `INPUT_STUFF_SPEC_MISMATCH` — so `sync-controller-inputs` keeps the user's marker whenever concept + multiplicity already match, and only derives markers for inputs it adds.
- **Prerequisite-clean rule**: a fix is only emitted when its inputs are trustworthy. If a pipe also has `UNRESOLVED_PIPE_DEPENDENCY` / `UNRESOLVED_CONCEPT` errors, `needed_inputs()` is incomplete — the planner must not emit `sync-controller-inputs` for it. Generally: co-errors on the same pipe that undermine the derivation suppress the fix for that iteration (the loop picks it up next round once the prerequisite is fixed).
- **Multi-file libraries**: fixes target the file that *declares* the item (`ValidationErrorItem.source`), and only files the user passed to the command get written. Cross-package qualified refs are never rewritten.

## CLI surface (wave 1)

- `pipelex-agent fix bundle <files...>` (and the `pipelex fix` mirror), symmetric with `validate`. Flags: `-L/--library-dir`, `--diff` (show, don't write), `--select`/`--ignore` (mutually exclusive, rule codes), `--max-iterations`, `--format`/`--error-format` per the two-stream convention (markdown default on the agent CLI).
- `pipelex-agent validate` output gains the `suggested_fix` annotations automatically (same report) — agents benefit even without running `fix`.
- Contract vs presentation: the machine verdict is the structured body (`is_valid` after fixing, `fixes_applied[]`, remaining `validation_errors[]`). Exit codes are presentation: 0 = valid after fixes (or already valid), 1 = still invalid, 2 = no verdict (infra/args).
- The markdown renderer for fix results lives beside `validation_render.py` (CLI-free module) so the API can reuse it in wave 2.

## Testing (TDD)

- **Planner unit tests**: enriched typed error → expected `SuggestedFix` ops, per rule, including suppression cases (prerequisite co-errors, synthetic pipes, signature pipes, cross-package refs).
- **Applier golden tests**: fixture `.mthds` files with comments, mixed inline/block styles, deliberate ordering → apply ops → byte-compare against golden output. This is the regression net for format preservation, the thing the old branch never proved. Include idempotence (apply twice = same bytes).
- **Convergence tests**: a fixture needing multiple iterations (cascade); a deliberately non-convergent fixture that must bail cleanly with the no-progress report.
- **e2e CLI tests**: `fix bundle` JSON and markdown snapshots; `validate` output showing `suggested_fix` annotations.

## Phases

### Phase 0 — Spike: prove the chain end-to-end

One rule (`match-sequence-output`) through all three layers: enrich the `INADEQUATE_OUTPUT_*` errors with the expected output ref (concept + multiplicity — `provided_concept_code` exists but multiplicity needs adding), planner translation, tomlkit applier with the guarded/idempotent semantics, minimal loop, red-green tests at each layer. No CLI command yet — driven by tests.

**CHECKPOINT 0**: chain proven or design revised. Update this doc with findings (especially: does tomlkit in-place mutation preserve style as expected; what the enriched-error shape settled to).

**CHECKPOINT 0 findings (2026-07-07 — chain proven, design holds):**

- **tomlkit in-place mutation preserves style as promised.** Assigning `table["output"] = value` keeps the trailing comment *on the patched line itself*, plus all comments, key alignment, ordering, and inline/block table styles of untouched content. Golden byte-comparison tests pin it (`tests/data/fixes/`), including idempotence.
- **Enriched-error shape settled**: `expected_output_ref: str | None` on `PipeValidationError`, threaded to `PipesAndConceptValidationErrorData` by `categorize_pipe_validation_with_libraries_error`. Only the two `PipeSequence` raise sites set it — which is also the suppression mechanism: the planner requires the field, so PipeParallel / PipeCondition / operator `INADEQUATE_OUTPUT_*` errors are structurally unfixable, no pipe-type sniffing needed. Rendering: bare concept code when same-domain or native, qualified `domain.Code` otherwise; effective multiplicity honors the sub-pipe override; presence marker rides via `format_concept_with_multiplicity`. Kept internal (error-data only) — the wire gets only `suggested_fix` (D-R3).
- **Wire models** live in the new low-level `pipelex/suggested_fix.py` (stdlib + pydantic only) so `base_exceptions.py` imports it cycle-free. `ValidationErrorItem.suggested_fix` is additive; non-fixable items serialize byte-identically (pinned).
- **Loop mechanics verdict: works as designed.** `fix_bundle_file` reuses `validate_bundle` wholesale; fingerprint = `fix_code|source|per-op(kind:path:key:value)` string; bail fires when an iteration proposes only already-seen fingerprints (pinned via a synthetic-pipe skip that would otherwise spin); `iterations` counts apply rounds; one final validate decides the verdict after `max_iterations`. Cascade fixture (nested sequences) converged in 2 rounds — note validation aborts at the *first* `PipeValidationError`, so multi-error bundles converge error-by-error across iterations rather than batch-applying; fine for correctness, worth remembering for loop-count expectations in Phase 1.
- **One deviation**: `RENAME_TABLE_KEY` exists on the wire enum (per the sketch) but the applier raises `PipelexUnexpectedError` for it — position-preserving rename is Phase 1 work gated on the strip-namespace mechanics; no spike planner emits it.
- **Tooling gotchas for Phase 1**: golden `.mthds` fixtures are processed by `plxt format` during `make agent-check`, so fixtures must be format-stable (write them, run the formatter, then derive the golden); `plxt lint` needs `derived/mthds_schema.json` regenerated (`pipelex-dev generate-mthds-schema`) in fresh clones/worktrees.

### Phase 1 — Engine + remaining wave-1 rules

Harden the loop (fingerprint bail, multi-file targeting), add `sync-controller-inputs` (with the optionals-marker and prerequisite-clean guards) and `strip-native-concept-redecl`. Attempt position-preserving rename; ship `strip-namespace` only if it lands clean. `suggested_fix` lands on `ValidationErrorItem`.

**CHECKPOINT 1**: all wave-1 rules green with golden format-preservation tests. Decisions on strip-namespace recorded here.

**CHECKPOINT 1 findings — `sync-controller-inputs` (2026-07-07, step-2 Phase A):**

- **Enrichment shape settled as a *pair* of mappings**: `expected_inputs` (what the pipe should declare) **and** `declared_inputs` (what it declares today), both `dict[str, str] | None`, both rendered domain-relative, on `PipeValidationError` → `PipesAndConceptValidationErrorData`. The pair keeps the planner pure: it diffs two mappings instead of needing file access, and emits `set_key` per added/changed variable + `delete_key` per extraneous one (deterministic order → stable fingerprints). This is the first multi-op fix; `SuggestedFix`/`FixOp` absorbed it unchanged.
- **Rendering factored to `StuffSpec.to_bundle_representation(relative_to_domain=...)`** — the spike's inline rendering in `PipeSequence` now reuses it; declared-spec renderings preserve the author's `?`/`!` markers when concept+multiplicity already match (presence is deliberately outside the drift contract).
- **Only the raise sites holding `the_needed_inputs` are enriched.** The `required_variables()` site stays bare: for a PipeCondition it fires for expression variables whose needed spec would come from the declared inputs themselves (unknowable, and `needed_inputs()` raises `InputStuffSpecNotFoundError` there). Suppression stays structural.
- **Prerequisite-clean guard needed no code**: library validation resolves all pipe dependencies (raising `UNRESOLVED_PIPE_DEPENDENCY` immediately) *before* any `validate_with_libraries()` runs, and skips controllers with unresolved cross-package deps — co-occurrence is impossible by ordering; pinned by test.
- **PipeLLM's missing/extraneous prompt-variable errors live on the blueprint channel** (static validation at model construction, reconstructed from pydantic messages), not the pipe-validation channel — structurally out of the planner's reach, pinned by test.
- **`TomlValue` widened** to `TomlScalar | dict[str, TomlScalar]` for the no-`inputs`-table case (one `set_key` writes the whole mapping as an inline table). First container value on the wire enum's `value` slot; nothing else bent.
- **Applier finding — inline-table canonicalization (superseded by Phase A′; kept for history).** tomlkit's incremental edits inside inline tables leave non-canonical whitespace (`{ a = "x",  b = "y"}`). The Phase A cut hand-canonicalized this in the applier (re-emit the mutated inline table with `{ key = value, ... }` spacing, trivia transplant), and the checkpoint-A review corrected the string-assembly crashes by building via `tomlkit.inline_table()` + outer-brace splice. **Phase A′ deletes all of that** — see the next section. The reviewers' recurring "why not just use `plxt`?" question is exactly what A′ answers: the *runtime* toolchain library `pipelex-tools-py` (in-process, distinct from the `plxt` CLI dev-dep) now owns canonical formatting.

**CHECKPOINT 1′ — `format_mthds` canonical-output backend (2026-07-07, step-2 Phase A′):**

- **Decision (Louis): ADOPT `pipelex_tools.format_mthds` as the single source of canonical style.** Added `pipelex-tools-py` as a **core runtime dependency** (import `pipelex_tools`; the in-process PyO3 extension built from `vscode-pipelex/crates/pipelex-py`, *distinct* from the `pipelex-tools` CLI-binary dev-dep — same `taplo`/MTHDS engine as `plxt`, embedded schema, offline, PEP 561 stubs; already a runtime dep of `pipelex-api`, precedent). This dissolves the "why not plxt?" tension: the earlier objection (dev-only Rust binary, no Python API, whole-file, breaks surgical byte-preservation) doesn't apply to the in-process library, and the fix tool *wants* whole-file canonical output anyway.
- **Applier is now pure mutation.** Deleted the hand-rolled `_canonical_inline_table` and `_canonicalize_mutated_inline_table` (and their two call sites). `apply_fix_ops` mutates the tomlkit DOM and stops there. The new `applier.serialize_and_format(toml_doc) -> str` dumps the DOM and hands it to `format_mthds`, which reflows inline-table/array spacing to canonical form; a `kind="syntax"` diagnostic means the applier emitted malformed TOML → `PipelexUnexpectedError` (never silently written). `fix_loop` writes `serialize_and_format(...)` instead of `save_toml_to_path(...)`.
- **Output philosophy shift (intended): surgical byte-preservation → canonical whole-file MTHDS.** Correct for a file-rewriting fix tool, and a no-op on already-formatted files (the norm — MTHDS is formatted on save + CI-enforced). Consequence surfaced by the loop tests: on a *hand-drifted, unaligned* fixture the formatter column-aligns single-line tables (`output = "x"` → `output   = "x"`), so convergence-test assertions moved from whitespace-coupled string counts to semantic reload checks (parse the fixed file, assert field values). This is the A′ design *working*, not a regression — re-validation passing already proves the fixes are correct.
- **Deviation from the literal plan, recorded:** the plan said "pass a plain dict on the whole-mapping `SET_KEY`, `format_mthds` canonicalizes it." Empirically a plain-dict assignment makes tomlkit emit a **detached `[pipe.x.inputs]` block table at end-of-file**, and `format_mthds` preserves block-vs-inline (it doesn't convert). So `_as_tomlkit_value` keeps a **minimal** `tomlkit.inline_table()` builder (no string-splicing, no brace-padding — the fragile parts are gone; tomlkit owns key quoting/value rendering, `format_mthds` owns spacing) so a freshly-created mapping stays inline and attached to its pipe. This reproduces every existing golden byte-for-byte (no golden regeneration needed) and gives strictly nicer output than a detached block table.
- **Goldens are now the `format_mthds` canonical output.** The applier golden tests (`test_fix_applier*.py`) route byte-compares through `serialize_and_format`; the F1 dotted-key and F2 whole-pipe-inline regression tests pass *by construction* now (the real parser can't crash on valid TOML, unlike the deleted hand-rolled canonicalizer). All four pre-existing goldens were unchanged.
- **`pipelex_tools` stub/runtime drift gotcha (found during review triage).** The PEP 561 stub declares `Diagnostic` / `Range` / `FormatResult` / `LintResult` in `__all__`, but those are **type-only** TypedDicts — not runtime exports of the compiled module. So `from pipelex_tools import Diagnostic` type-checks (pyright/mypy read the stub) yet raises `ImportError` at runtime. `applier.py` imports `Diagnostic` under a `TYPE_CHECKING` guard (quoted annotation) and imports only the real callable `format_mthds` at runtime. Since `pipelex-tools-py` is ours, Louis is fixing the drift upstream; the follow-up to simplify our workaround once it ships is tracked in [deferred-checkpoint-a-prime-review-items.md](deferred-checkpoint-a-prime-review-items.md) (item 1), which also carries a Phase-C exploration note (item 2: an upstream rename / canonical-ordering primitive, since `format_mthds` reflows spacing but does not reorder tables).

**CHECKPOINT B — `strip-native-concept-redecl` (2026-07-07, step-2 Phase B): blueprint channel opened end-to-end.**

- **The blueprint channel now runs the planner.** `build_validation_error_items`' blueprint loop calls `plan_fix_for_blueprint_validation_error(...)`, mirroring the pipe loop — so a blueprint-validation error can now ride a `suggested_fix`. This is the first fix that is **not** a pipe-validation fix and the first whose `SuggestedFix.source` is populated from real validation (blueprint error data carries `source` from `blueprint_dict["source"]`; the pipe raise sites still emit `source=None`).
- **Enrichment = typed raise + structural unwrap, no message matching.** `validate_concept_keys` raised a bare `ValueError` whose only carrier of the offending concept code was the message text (pydantic `loc` is just `("concept",)`, so the concept categorizer produced `error_type=None`, `concept_code=None`). Replaced it with `NativeConceptRedeclarationError(ValueError)` carrying `concept_code`; because it subclasses `ValueError`, a `mode="before"` field validator can raise it and pydantic preserves it in `ctx["error"]`. The blueprint categorizer unwraps it structurally (`_extract_wrapped_native_concept_redeclaration_error`, the exact pattern of `extract_wrapped_pipe_validation_error`) — placed **before** the scope dispatch so it wins over the un-enriched concept-scope path. The other bare `ValueError` in the same validator (invalid concept-code *syntax*) is left untyped → stays uncategorized → no fix (structural suppression; pinned by test).
- **Enum home decision: widen the shared `PipeValidationErrorType`, do not add a new enum.** The field type of `PipelexBundleBlueprintValidationErrorData.error_type` is `PipeValidationErrorType | None`, and that enum is already the de-facto MTHDS *validation-error-type* enum (it holds concept-scope values like `UNRESOLVED_CONCEPT`), despite the legacy `Pipe`-prefixed name. Added `NATIVE_CONCEPT_REDECLARATION` there — smallest correct surface, field type unchanged, wire projection unchanged. Did **not** resurrect the deleted `PipelexBundleBlueprintFixableErrorType` stub. Cost: the enum has exhaustive `@property` match/case methods, so the new value had to be added to `is_controller_input_drift` / `is_inadequate_output` (False arms) and a new single-case `is_native_concept_redeclaration` property added (house style: single-out-one-case via a property, never enum equality).
- **The applier needed no new code.** `DELETE_KEY` on `["concept"]` (key = the offending code) covers **every** authoring form — `[concept.X]` table (incl. a `[concept.X.structure]` sub-table, deleted with it), `X = "…"` string shorthand under `[concept]`, and dotted `concept.X` — because tomlkit represents all three as a `concept` table keyed by the code. `format_mthds` keeps dotted keys dotted (just column-aligns), so a dotted fixture is a genuine, format-stable authoring form. Golden byte-compare across all three forms.
- **Source-guard first live exercise.** With a populated `source`, the loop's `Path(source) == mthds_file_path` check applies the fix single-file (convergence test) **and** under `library_dirs` when the source is the file being fixed (positive complement to the pre-existing source-*less*-dropped test). Multi-redeclaration bundles converge error-by-error (the `mode="before"` validator raises on the first offending code per pass) — the same cascade shape as the pipe channel, now on the blueprint channel.
- **Known minor artifact (not fixed, low value):** deleting a `[concept.X]` table whose *leading* line is a standalone comment reflows that comment onto the successor element (tomlkit trivia behavior; `format_mthds` doesn't reposition it). Comments on *untouched* content are preserved (that is the guarantee). Fixtures put comments on surviving content to keep the goldens clean; a comment sitting directly on the deleted concept is the only thing that can dangle. Acceptable for a fix tool whose output the author reviews (and which CI reformats).
- **Abstraction verdict so far:** `SuggestedFix`/`FixOp` absorbed the delete-shaped fix and the blueprint channel **unchanged** — the only new wiring was one planner function + one builder-loop call. The remaining stress (position-preserving rename, array-of-tables addressing) is Phase C's to produce.

**CHECKPOINT C — `strip-namespace` rename-mechanics spike (2026-07-07, step-2 Phase C.1): the gate opens.**

The spike answered both gating questions in favor of building the rule, and — unexpectedly — the scary one dissolves entirely:

- **Position-preserving rename is achievable.** tomlkit's `Container._replace(old_key, new_key, item)` renames a `[pipe]` sub-table key **in place**: it does `self._body[idx] = (new_key, value)` and `value.invalidate_display_name()`, so the renamed table keeps its position among siblings, its leading standalone comment and trailing inline comments, and re-renders the header with correct quoting (`[pipe."greetings.hello"]` → `[pipe.hello]`). The old `feature/Bundle-fixer` reordering bug came from `del` + re-add (append semantics send the pipe to the bottom); `_replace` sidesteps it. Verified end-to-end in the **full runtime context** — after `Pipelex.make()` + a real `validate_bundle`, serialized through `format_mthds` (no syntax diagnostics), then re-validated VALID — plus idempotence (re-apply skips: key absent) and collision suppression (bare code already declared → skip). The single wart: `_replace` is a tomlkit **private** method; a golden byte-compare test is the CI tripwire if a tomlkit bump changes its semantics (pin is `tomlkit>=0.13.2`). `format_mthds` does not reorder tables, so no upstream ordering primitive was needed — dissolving the Phase-C exploration note (item 2 of [deferred-checkpoint-a-prime-review-items.md](deferred-checkpoint-a-prime-review-items.md)).

- **The array-of-tables addressing gap NEVER needs crossing** — this is the decisive finding, and it inverts the plan's premise. The plan assumed `strip-namespace` must rewrite every internal reference (`steps[].pipe`, `branches[].pipe`, …) to the renamed pipe, and that addressing items inside arrays would force a `FixOp.table_path` extension. Two empirical facts collapse that whole line of work: **(1)** a same-domain **qualified** reference (`greetings.hello`) already resolves to the bare pipe `hello` in domain `greetings` (pinned by validating a bundle whose `steps[].pipe` uses the qualified form against a bare declaration → VALID); **(2)** **no** controller reference field runs a snake_case check — only the pipe-declaration keys (`validate_pipe_keys`) and `main_pipe` (`validate_main_pipe_syntax`) do. So the *only* things that make a same-domain-dotted bundle invalid are the **declaration key** and (if the author over-qualified it) **`main_pipe`**. Fixing those — a rename of the `[pipe]` key and a root `set_key` — makes the bundle valid; the `steps[].pipe` references keep resolving untouched (leaving them qualified is a style nit, not a validity error, and normalization is a wave-2 lint concern per D4). **`FixOp.table_path: list[str]` stays unchanged; no index segments, no new op kind.**

- **Architecture: the same Phase B pattern, no blueprint needed.** `INVALID_PIPE_CODE_SYNTAX` is raised in a `mode="before"` validator, so the blueprint never constructs and `collect_pipe_references()` is unavailable — but since references need no rewrite, the planner needs only the offending code + stripped code + which site (pipe key vs `main_pipe`), all rideable on a typed exception exactly as `NativeConceptRedeclarationError` carried `concept_code` in Phase B. No planner→blueprint access, no message matching.

- **Verdict: GO** (Louis confirmed 2026-07-07) — **implemented and landed.** Rationale: the mechanics gate is clean, the abstraction holds **unchanged** (the strongest possible verdict is proving `RENAME_TABLE_KEY` end-to-end rather than declaring it unproven), and the implementation is small and follows Phase B. The rule's niche trigger (a quoted-dotted declaration `[pipe."domain.code"]`, typically machine-generated) is a minor concern for an opt-in fix that costs nothing when not triggered.

**CHECKPOINT C outcome — `strip-namespace` landed:**

- **Enrichment = typed raise + structural unwrap, no message matching** (the Phase B pattern). `InvalidPipeCodeSyntaxError(ValueError)` carries `offending_code` + `stripped_code`, raised at `validate_pipe_keys` / `validate_main_pipe_syntax` **only when safely strippable** (the `_strippable_same_domain_pipe_code` gate: prefix == own `domain`, valid snake_case bare tail, and for a declaration no collision with an existing bare key). Both validators gained an `info: ValidationInfo` param to read `domain` from `info.data` (field order guarantees `domain` is validated first). The categorizer unwraps structurally and sets `stripped_pipe_code`, with `pipe_code` discriminating the two raise sites (offending dotted key for a rename; `None` for `main_pipe`, read from `loc`). Bare-`ValueError` codes (malformed, cross-package) still flow through the message-matching categorizer → `INVALID_PIPE_CODE_SYNTAX` without `stripped_pipe_code` → unfixable.
- **`RENAME_TABLE_KEY` is the last op kind, now proven.** The applier implements it via tomlkit's position-preserving `Container._replace` (reached through `_container_of`, since a `Table`'s dict facade doesn't expose it), with guarded skips on key-absent and collision. `main_pipe` reuses the existing root `SET_KEY`. `new_key` joined `_fix_fingerprint` (deferred item 1b closed).
- **Abstraction verdict: `SuggestedFix`/`FixOp` absorbed the rename-shaped fix UNCHANGED.** No wire-model change (no `table_path` widening, no new op kind — `RENAME_TABLE_KEY` was already on the enum), only its applier implementation + one planner branch + one enum property + one error-data field. This completes the wave-1 stress test: multi-op (Phase A), delete-shaped + blueprint channel (Phase B), and rename-shaped (Phase C) all rode the abstraction without bending it.
- **The one wart: reliance on tomlkit's private `Container._replace`.** It is tomlkit's own internal position-preserving primitive (what `__setitem__` uses to re-home an existing key); the public API only offers `del` + re-add, which appends to the bottom. The golden byte-compare test (`test_fix_applier_strip_namespace.py`) is the CI tripwire if a tomlkit bump changes its semantics (pin is `tomlkit>=0.13.2`).
- **Deviation from the plan's literal C.2 tasks (recorded):** the plan expected reference-rewrite ops driven by `collect_pipe_references()` and an array-of-tables addressing decision. Both were dropped: the C.1 spike proved same-domain qualified refs resolve, so references need no rewrite, and `collect_pipe_references()` is unavailable anyway (the blueprint aborts construction in a `mode="before"` validator). The fix strips only the two snake_case-enforcing sites.

### Phase 2 — CLI + docs + changelog

`pipelex-agent fix bundle` + `pipelex fix` commands, two-stream output, docs page (`docs/`), CHANGELOG entry ([Unreleased]). Update the `mthds-fix` skill guidance is wave-2 territory (plugins repo), but note the hand-off. Sequencing inside this phase is deliberate — agent command first, human CLI (`pipelex fix` + the `💡 Suggested fix` line in `validate`) last and gated on rule breadth + the apply command existing; see the master plan's "Sequencing doctrine".

**CHECKPOINT 2**: wave 1 shippable. `make agent-check` + `make agent-test` green. Record the hand-off list for wave 2.

### Wave 2 (separate plan, not scoped here)

Protocol promotion (spec sections in `docs/specs/`, conformance arm, schema sync to mthds / mthds-js / mthds-python), API `POST /fix`, MCP `mthds_fix` tool, VS Code `CodeActionProvider` (first code action in the LSP — keyed on `diag.code = error_type`, fix payloads already ride the validation backends), `mthds-fix` / pipelex-plugins skill updates, pruning rules as lint warnings with attached fixes.

## Salvage map from `feature/Bundle-fixer`

Worth harvesting (as reference, reimplemented under TDD): the `needed_inputs()` sync semantics and diff-message construction; the last-step-output derivation incl. multiplicity override; the `_should_strip` namespace guard (strip only when prefix == own domain AND bare code exists locally); the reachability BFS + concept transitive closure (for wave-2 pruning lints). Not worth harvesting: the orchestrator (parallel validation pipeline), the single-pass model, the inline-table rebuild, the unpopulated `line` field, the pyright blanket suppressions.
