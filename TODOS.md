# Implementation plan — PipeSignature is not a type

**Branch:** `feature/PipeSignature-not-a-type`
**Design doc:** [`wip/pipe-signature-not-a-type.md`](wip/pipe-signature-not-a-type.md) — read this first for the *why*.
**Status:** NOT STARTED · Phase 0/3

## Goal in one line

Drop `type = "PipeSignature"` from the language: a `[pipe.x]` section with **no `type`** and **nothing but the contract** (`description` + `output`, optional `inputs`, optional `signature_for`) **is** a `PipeSignature`. Anything else without a `type` is a hard error.

## Settled decisions (from the design doc)

- **D1** — Signatures only. Concrete pipes keep explicit `type`. No inference from fields (impossible anyway — `prompt` is shared by PipeLLM and PipeImgGen).
- **D2** — Typeless + any non-contract field ⇒ **hard error**, no leniency, no type-guessing. Legal typeless keys are exactly `{description, inputs, output, signature_for, source}`.
- **D3** — Explicit `type = "PipeSignature"` ⇒ **rejected** with a migration error. No transitional alias.
- **D4** — Keep the optional `signature_for` hint.

## Phasing rationale (why this order)

`make agent-check` runs `plxt-lint`, which **regenerates the JSON schema from the Python models and then lints every `.mthds` file against it** (Makefile:842-845). So the language-schema generator and the fixture migration are gate-locked: fixtures can only drop the tag once the schema accepts typeless sections. To keep every checkpoint green *and* reviewable in isolation, we go **additive first, breaking last**:

- **Phase 1** makes typeless-signatures work at runtime *and* in the schema, while the old explicit tag still parses (both accepted). Tested with inline TOML/dicts so no fixture files move yet.
- **Phase 2** mirrors the same additive support in the spec (authoring) layer.
- **Phase 3** flips to rejecting the old tag, migrates all fixtures, rewords rendering, and updates docs — the one breaking phase.

One commit per phase (repo convention). Nothing pushed until the user says so.

---

## Fan-out convention for `/code-review` (used at every checkpoint)

Spawn the reviewer as a **fresh Sonnet-5 sub-agent with NO inherited context** (`subagent_type: general-purpose`, `model: sonnet` — **not** `fork`, which would inherit this plan). Hand it *only* a pointer to the changes:

> Run the `/code-review` skill on the changes in `<commit SHA>` (or `git diff <base>..HEAD`, or the unstaged working tree). We want clean, solid software — flag over-engineering, dead code, and any correctness bug. Report findings only; do not fix.

Do **not** pass the plan, the design doc, the decisions, or any rationale. Let the review land cold. Triage its findings back in TODOS.md (fix / defer-to-wip / refute) before clearing the checkpoint.

---

## Phase 0 — Baseline (quick)

- [x] Confirm branch is green from a clean state: `make agent-check && make agent-test`. — both green (exit 0).
- [x] Note the baseline SHA here for the Phase-1 review diff base: `04434f78586b328e080fd76b50bf46b00e0b6765`.

---

## Phase 1 — Additive typeless-signature support (blueprint + language schema)

The heart of the change. Make "no type + contract-only ⇒ signature" true at runtime and in the schema. Keep the old explicit tag parsing for now (rejection is Phase 3).

- [x] Introduce a single named constant for the legal signature-only key set `{description, inputs, output, signature_for, source}`. → `SIGNATURE_ONLY_KEYS` (frozenset) added next to `PIPE_SIGNATURE_TYPE_TAG` in `pipelex/core/pipes/pipe_blueprint.py`. Single source of truth for blueprint + (Phase 2) spec layers.
- [x] Extend the `pipe` `mode="before"` validator in `pipelex/core/bundles/pipelex_bundle_blueprint.py` (`validate_pipe_keys`) with per-section normalization (new helper `_normalize_typeless_signature`):
  - `type` present (or an already-built blueprint instance / non-dict) → untouched.
  - `type` absent, keys ⊆ `SIGNATURE_ONLY_KEYS` → inject internal `type = "PipeSignature"` so the union routes to `PipeSignatureBlueprint`.
  - `type` absent, any other key present → raise the **teaching error** (names the offending field(s), states the rule, gives both fixes; does **not** guess a type).
  - `type = "PipeSignature"` written explicitly → still accepted this phase.
- [x] Route the teaching error through the existing categorizer → new `MISSING_PIPE_TYPE` value on `PipeValidationErrorType` + `_categorize_missing_pipe_type_error` in `validation_error_categorizer.py` (the error is raised on the aggregate `pipe` field, so the pipe_code is recovered from the message; sits alongside `UNKNOWN_PIPE_TYPE`, category `blueprint_validation`).
- [x] Schema generator `pipelex/language/mthds_schema_generator.py`: **`_require_type_on_pipe_definitions` now skips the signature arm**, leaving its `type` OPTIONAL (Pydantic already emits `enum: ["PipeSignature"]` with a default). **Deviation from the literal checklist wording, intentional for Phase 1:** the design doc / this bullet describe the *end-state* (remove `type` from the signature arm → an explicit tag then fails the schema). Doing that in Phase 1 breaks every still-tagged fixture under `plxt-lint` (verified: `error[schema]: Additional properties are not allowed ('type' ...)`). Since Phase 1 is additive (both forms accepted, **no fixtures move yet**), the arm keeps `type` optional. Disambiguation verified for all cases: typeless contract → 1 match (signature arm); typeless+stray → 0; concrete typed → 1 (own arm); explicit `PipeSignature` → 1 (still valid); typo'd type → 0. **Removing `type` from the arm + migrating fixtures is the gate-locked Phase-3 breaking step.**
- [x] Regenerate the derived schema (`.venv/bin/pipelex-dev generate-mthds-schema`) — runs clean; `plxt lint` clean across all fixtures.
- [x] Tests (inline TOML/dicts — no fixture files yet), in `tests/integration/pipelex/pipe_signature/test_pipe_signature_in_blueprint_union.py`:
  - typeless contract ⇒ `PipeSignatureBlueprint`, `is_signature is True`, `pipe_category is None`.
  - contract with **no `inputs`** is valid.
  - typeless + a stray field ⇒ teaching error (asserts message names the field + both fixes).
  - explicit `type = "PipeSignature"` still accepted.
  - typeless header vs. typed definition reconciles (concrete wins) — added to `tests/unit/pipelex/libraries/test_dependency_multi_file_reconciliation.py`.
  - categorizer routing: `MISSING_PIPE_TYPE` structured item with pipe locator — added to `tests/integration/pipelex/pipeline/test_validate_bundle_structured_errors.py`.
- [x] Schema tests in `tests/unit/pipelex/language/test_mthds_schema.py`: typeless contract validates; typeless + stray field fails; typo'd `type` fails; explicit tag still validates (Phase-1 guard); `type`-required test now excludes the signature arm.
- [x] `make agent-check && make agent-test` green (full suite, exit 0).

### ⛔ CHECKPOINT 1 — STOP

- [x] Commit the phase (one commit). Record SHA: `7cdc429028650f0694380d7af415f431287935a0`.
- [x] Update the **Cold-start snapshot** below (what changed, where the seam lives, what's verified, what's next).
- [x] **Fan out** a fresh Sonnet-5 `/code-review` sub-agent on this commit's diff, per the fan-out convention above. Triage findings here:
  - Findings: cold Sonnet-5 review, no blocker/major (core mechanism verified correct: fresh dicts/no input mutation, deterministic message order, sound pipe-code regex recovery, correct Draft-4 `oneOf` disambiguation). Minor/nits only:
    - **F1 (minor)** — a typeless section that is a subset of the allowed keys but omits a required contract field (`description`/`output`) is injected as a signature, then fails with a bare uncategorized pydantic "Field required" residual (dropped from structured `validation_errors[]`). Reviewer confirmed **not a regression** (concrete `PipeLLM` missing `output` behaves identically today) and the safety invariant holds (errors, never silent mock).
    - **F2 (nit)** — the `source` comment on `SIGNATURE_ONLY_KEYS` overstated present behavior.
    - **F3 (nit)** — message↔categorizer coupling; already guarded (marker comment + integration test).
    - **F4 (nit)** — hardcoded counts in TODOS.
    - **F5 (context)** — spec layer not yet mirrored = Phase 2 by design.
  - Actions taken / deferred-to-wip: **F1** → added guard test `test_typeless_section_missing_required_contract_field_still_errors` (pins the safety invariant) + **deferred** the broader categorization-completeness fix to `wip/pipe-signature-not-a-type.md` (it's a pre-existing general gap whose fix also changes concrete-pipe categorization — out of scope here). **F2** → comment corrected (kept `source` per D2). **F3** → no change (adequately guarded). **F4** → counts removed. **F5** → no action (next phase). All folded into the Phase-1 commit (amended); revised SHA recorded below.
- [ ] Only then proceed to Phase 2.

---

## Phase 2 — Spec (authoring) layer

Mirror the additive support so AI-authored specs get the identical clean surface. Specs are the builder convenience format (`pipelex/builder/pipe/`); they convert via `to_blueprint()`.

- [ ] Add the same `mode="before"` normalization wherever spec dicts are validated into `PipeSpecUnion` (`pipelex/builder/pipe/pipe_spec_union.py` + the parse site). Reuse the signature-only key constant from Phase 1. Same three rules (explicit tag still accepted this phase).
- [ ] Confirm whether the spec layer has its own JSON-schema surface (e.g. a build/authoring API schema). If yes, apply the same signature-arm treatment; if no, note it here so the next session doesn't re-investigate: `__________`.
- [ ] Tests: typeless spec ⇒ `PipeSignatureSpec` ⇒ `to_blueprint()` ⇒ `PipeSignatureBlueprint` with matching contract; typeless spec + stray field ⇒ teaching error.
- [ ] `make agent-check && make agent-test` green.

### ⛔ CHECKPOINT 2 — STOP

- [ ] Commit the phase. Record SHA: `__________`.
- [ ] Update the **Cold-start snapshot** below.
- [ ] **Fan out** a fresh Sonnet-5 `/code-review` sub-agent on this commit's diff (fan-out convention). Triage:
  - Findings: `__________`
  - Actions taken / deferred: `__________`
- [ ] Only then proceed to Phase 3.

---

## Phase 3 — Breaking cleanup, fixture migration, docs

The one breaking phase: reject the old tag, migrate every bundle, reword rendering, update docs. Everything below lands green together because schema regeneration + fixture migration are gate-locked.

- [ ] Blueprint before-validator: `type = "PipeSignature"` written explicitly ⇒ **migration error** (D3): "`PipeSignature` is no longer a pipe type. Delete the `type` line — a pipe with no type and no implementation is a signature."
- [ ] Spec before-validator: same rejection.
- [ ] Schema generator: ensure the regenerated schema no longer lists `PipeSignature` as a selectable `type` value anywhere (the tag is internal-only now). Verify `plxt-lint` rejects an explicit `type = "PipeSignature"` in a `.mthds` file.
- [ ] Migrate the 8 bundle fixtures — delete the `type = "PipeSignature"` line from each (they become the typeless regression corpus):
  - `tests/e2e/fixtures/signature_bundles/signature_only.mthds`
  - `tests/e2e/fixtures/signature_bundles/mixed_with_signature_step.mthds`
  - `tests/e2e/fixtures/signature_bundles/signature_with_structured_output.mthds`
  - `tests/e2e/fixtures/signature_bundles/multi_input_multiplicity.mthds`
  - `tests/e2e/pipelex/pipes/additive_multi_file_library/header_and_definition/header.mthds`
  - `tests/e2e/pipelex/pipes/additive_multi_file_library/signature_only/header.mthds`
  - `tests/e2e/pipelex/pipes/additive_multi_file_library/recursive_refinement/write_research_brief.mthds`
  - `tests/e2e/pipelex/pipes/additive_multi_file_library/recursive_refinement/bundle.mthds`
- [ ] `pipe_signature_spec.py` `rendered_pretty`: drop the `Type: PipeSignature (...)` line; present it as "Signature (contract only)".
- [ ] Add a test asserting the migration error fires on an explicit tag (blueprint + spec).
- [ ] Docs — teach "omit the type," remove the `type = "PipeSignature"` idiom:
  - `docs/building-methods/pipes/signature-pipes.md`
  - `docs/building-methods/pipes/index.md`
  - `docs/tools/cli/validate.md`, `docs/tools/cli/agent-cli.md`
  - `docs/errors/pipe-signature-not-executable-error.md`, `docs/errors/authoring-and-language.md`, `docs/under-the-hood/error-model.md`
  - `pipelex/cli/agent_cli/CLAUDE.md`
- [ ] CHANGELOG.md `[Unreleased]`: **breaking** — `type = "PipeSignature"` removed; a typeless contract-only pipe is now a signature. Note the JSON-schema shape change.
- [ ] `make agent-check && make agent-test` green (full suite, not targeted — this is the wrap-up).

### ⛔ CHECKPOINT 3 — STOP (final)

- [ ] Commit the phase. Record SHA: `__________`.
- [ ] Update the **Cold-start snapshot** below to the finished state.
- [ ] **Fan out** a fresh Sonnet-5 `/code-review` sub-agent on this commit's diff (fan-out convention). Triage:
  - Findings: `__________`
  - Actions taken / deferred: `__________`
- [ ] Record the **gated cross-repo follow-up**: the MTHDS JSON Schema copies in `mthds`, `vscode-pipelex`, `mthds-ui` drift (signature arm no longer requires `type`). Propagate via the `mthds-schema-sync` skill, **gated on the released pipelex version** — not on this branch.
- [ ] Hand back to the user for review / merge decision (do not push unprompted).

---

## Invariants to preserve (regression guardrails — do not break)

- Reconciliation keys off `is_signature` class identity (`library_crate_factory.py:170-201`): concrete beats signature, contracts must match, two matching signatures tie-break deterministically. Untouched by this change — add a regression test, don't refactor.
- Strict validation still refuses bundles that contain a signature; `--allow-signatures` still dry-runs signatures as mocks (`validate_bundle.py`, `cli/commands/validate/_validate_core.py`). Keyed off the pending-signatures set / `is_signature`. Untouched.
- `PipeSignature` stays a valid **internal** discriminator value (the before-validator injects it); it is only rejected as a **user-written** value. Don't remove it from `valid_pipe_type_tags()` without confirming the injected value still passes `validate_pipe_type`.

---

## Cold-start snapshot (updated at each checkpoint)

> Keep this current so a fresh session can resume with zero re-investigation. Template to fill at each checkpoint:
>
> - **Phase reached / last green SHA:** …
> - **What changed and where the seam lives:** …
> - **What is verified (tests/gates run):** …
> - **Open threads / review findings deferred:** …
> - **Exact next action:** …

- **Phase reached / last green SHA:** Phase 1 complete (additive typeless-signature support). Baseline (review diff base) = `04434f78586b328e080fd76b50bf46b00e0b6765`. Phase-1 commit SHA = `7cdc429028650f0694380d7af415f431287935a0`.
- **What changed and where the seam lives:**
  - The single choke point is `PipelexBundleBlueprint.validate_pipe_keys` (`pipe`, `mode="before"`) in `pipelex/core/bundles/pipelex_bundle_blueprint.py`, with the new helper `_normalize_typeless_signature`. A typeless `[pipe.x]` whose keys ⊆ `SIGNATURE_ONLY_KEYS` gets `type = "PipeSignature"` injected (routes to `PipeSignatureBlueprint`); a typeless section with any other key raises the teaching error; a section that already names a `type` (or is a built blueprint instance) is untouched. Runs *before* the discriminated union, so it intercepts what used to be `union_tag_not_found`.
  - `SIGNATURE_ONLY_KEYS` (frozenset `{description, inputs, output, signature_for, source}`) lives next to `PIPE_SIGNATURE_TYPE_TAG` in `pipelex/core/pipes/pipe_blueprint.py` — the single source of truth the Phase-2 spec layer will reuse.
  - Error surfacing: `PipeValidationErrorType.MISSING_PIPE_TYPE` (new) + `_categorize_missing_pipe_type_error` in `validation_error_categorizer.py`. The teaching error is raised on the aggregate `pipe` field (loc `("pipe",)`, no pipe_code), so the categorizer recovers the pipe_code from the message via a stable marker (`_MISSING_PIPE_TYPE_MARKER = "has no `type` but declares"`). Category = `blueprint_validation`.
  - Schema: `_require_type_on_pipe_definitions` in `mthds_schema_generator.py` **skips** the signature arm (`_SIGNATURE_DEFINITION_NAME`), leaving `type` optional (`enum: ["PipeSignature"]`). See the Phase-1 schema note above — this is the additive shape; Phase 3 removes `type` from the arm (breaking) + migrates fixtures in the same commit.
- **What is verified (tests/gates run):** `make agent-check` fully green (ruff/plxt/pyright-0/mypy-0/keyword-only). `plxt lint` clean across all still-tagged fixtures. Targeted suite (schema + blueprint-union + reconciliation + structured-errors) all pass. Full `make agent-test` green (exit 0). Disambiguation matrix hand-verified (typeless→1, stray→0, typed→1, explicit-tag→1, typo→0).
- **Invariants confirmed untouched:** reconciliation keys off `is_signature` (regression test added with a typeless header); `PipeSignature` stays a valid internal discriminator (`valid_pipe_type_tags()` unchanged; injected value passes `validate_pipe_type`).
- **Open threads / review findings deferred:** Checkpoint-1 cold review found no blocker/major. One deferred item captured in `wip/pipe-signature-not-a-type.md` → "Deferred follow-ups": categorizing the bare pydantic residual for a typeless section missing a required contract field (a pre-existing general gap that also affects concrete pipes). Safety invariant is guarded by a test.
- **Exact next action:** Phase 2 — mirror the same additive normalization in the spec (authoring) layer: `PipeSpecUnion` is validated via `bundle_spec.py` `pipe: dict[str, PipeSpecUnion]` and `pipelex/builder/operations/pipe_ops.py` (`spec_class.model_validate`). Add a matching `mode="before"` normalization reusing `SIGNATURE_ONLY_KEYS`. Confirm whether the spec layer has its own JSON-schema surface (note the finding in the Phase-2 checklist).
