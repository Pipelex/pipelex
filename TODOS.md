# Implementation plan — PipeSignature is not a type

**Branch:** `feature/PipeSignature-not-a-type`
**Design doc:** [`wip/pipe-signature-not-a-type.md`](wip/pipe-signature-not-a-type.md) — read this first for the *why*.
**Status:** Phase 2 complete · Checkpoint 2 cleared · next = Phase 3 (breaking cleanup, fixture migration, docs)

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

- [x] Commit the phase (one commit). Record SHA: `e864b82486f00502206c6aa11b609b5256392e30`.
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

- [x] Add the same `mode="before"` normalization wherever spec dicts are validated into `PipeSpecUnion`. **The one production dispatch site for raw typeless dicts is `PipelexBundleSpec.pipe: dict[str, PipeSpecUnion]`** (`pipelex/builder/bundle_spec.py`) — added a `@field_validator("pipe", mode="before")` (`validate_pipe_keys`) that mirrors the blueprint layer. To avoid message drift with the categorizer marker (Phase-1 F3), the normalizer was **extracted into a single shared free function** `normalize_typeless_signature_section(pipe_code, *, pipe_section, allowed_keys)` in `pipelex/core/pipes/pipe_blueprint.py` (next to `SIGNATURE_ONLY_KEYS`); both the blueprint's `validate_pipe_keys` and the spec's now call it. The blueprint's old `_normalize_typeless_signature` classmethod was removed. **Key-set difference:** a spec section carries the structural `pipe_code` field (the blueprint uses the dict key), so the spec passes `SIGNATURE_ONLY_SPEC_KEYS = SIGNATURE_ONLY_KEYS | {"pipe_code"}` (defined in `bundle_spec.py`).
  - **Second candidate site investigated & ruled out:** `pipe_ops.py` `parse_pipe_spec` (`spec_class.model_validate`) and its only caller, the agent-CLI single-pipe `pipe` command (`pipe_cmd.py`), **always resolve an explicit type upstream** — `pipe_cmd.py:266` hard-errors if neither `--type` nor a `type` key is given, and `parse_pipe_spec` sets `spec_data["type"]` before validating. So a typeless dict never reaches that `model_validate`; no normalization is reachable there in Phase 2. `--type PipeSignature` still works there today (it's in `pipe_type_to_spec_class`). **Phase-3 gap flagged** (see below).
- [x] Confirm whether the spec layer has its own JSON-schema surface (e.g. a build/authoring API schema). If yes, apply the same signature-arm treatment; if no, note it here so the next session doesn't re-investigate: **No dedicated authoring schema.** The only generated/committed JSON Schema is `derived/mthds_schema.json`, produced from the **blueprint** layer (`mthds_schema_generator.py` → `PipelexBundleBlueprint.model_json_schema()`, handled in Phase 1). The spec models (`PipeSpecUnion` / `PipelexBundleSpec`) call `model_json_schema()` only ad-hoc for dry-run mock formats (`json_schema_extra={"mock_format": ...}`); the signature spec already hides its internal tags with `SkipJsonSchema[...]` on `type`/`pipe_category`. Nothing to regenerate or sync for the spec layer.
- [x] Tests: typeless spec ⇒ `PipeSignatureSpec` ⇒ `to_blueprint()` ⇒ `PipeSignatureBlueprint` with matching contract; typeless spec + stray field ⇒ teaching error. → `tests/unit/pipelex/builder/test_bundle_spec_typeless_signature.py` (also covers `signature_for` hint, explicit-tag-still-accepted Phase-2 guard, typed-section-untouched, already-built-instance passthrough).
- [x] `make agent-check && make agent-test` green. — agent-check: ruff/plxt/pyright-0/mypy-0/keyword-only all pass; full agent-test exit 0 ("All tests passed").

**Phase-3 gap flagged (single-pipe signature authoring):** once Phase 3 rejects the explicit `type = "PipeSignature"`, the agent-CLI single-pipe `pipe` command will have **no way to author a signature** (can't pass `--type PipeSignature` any more, and `pipe_cmd.py` errors on absent type). Phase-3 decision: either (a) make `pipe_cmd.py`/`parse_pipe_spec` route a typeless spec to `PipeSignatureSpec`, or (b) accept that signatures are only authored at the bundle level. Not implemented now (belongs with the breaking phase).

### ⛔ CHECKPOINT 2 — STOP

- [x] Commit the phase. Record SHA: `34fd87849866a37f0f0005b725de7ff21960ebe5` → **amended after review to `b52b4e8df5a21c2d521d59bd1a08b1d65e028f28`**.
- [x] Update the **Cold-start snapshot** below.
- [x] **Fan out** a fresh Sonnet-5 `/code-review` sub-agent on this commit's diff (fan-out convention). Triage:
  - Findings: cold Sonnet-5 review, **no blocker/major**. The shared-helper extraction was verified behavior-identical (full diff compare + all blueprint/schema/reconciliation/structured-error suites + new spec tests pass); before-validator confirmed to handle None / non-dict / raw-dict / already-built-instance identically to the blueprint. Two minor findings + one nit, both in the areas flagged for scrutiny:
    - **F1 (minor)** — `SIGNATURE_ONLY_SPEC_KEYS` reused `SIGNATURE_ONLY_KEYS` wholesale, carrying the **blueprint-only `source`** into the spec allowlist. `PipeSpec` has no `source` (extra="forbid"), so a typeless section with `source` was injected then failed with a raw pydantic `extra_forbidden` instead of the clean teaching error — defeating the Phase-2 goal for that key.
    - **F2 (minor)** — the spec's `validate_pipe_keys` only mirrored the *normalization* half of the blueprint's, not the **snake_case dict-key check**. A non-snake_case `[pipe.X]` key slipped through the spec layer and only failed later (worse-shaped, wrapped) in `to_blueprint()`. Docstring over-claimed "mirrors the blueprint layer."
    - **F3 (nit)** — the static teaching message lists only `description`/`inputs`/`output`, not `signature_for`/`source`/`pipe_code`.
  - Actions taken / deferred: **F1 → fixed** — `SIGNATURE_ONLY_SPEC_KEYS = (SIGNATURE_ONLY_KEYS - {"source"}) | {"pipe_code"}`; the allowlist now reflects the spec's real field surface. Guard test `test_typeless_with_blueprint_only_source_field_raises_teaching_error` (asserts teaching error, not raw `extra_forbidden`). **F2 → fixed** — added the same `is_pipe_code_valid` dict-key check to the spec's `validate_pipe_keys` (now a full mirror; docstring updated). Guard test `test_invalid_pipe_dict_key_rejected_at_spec_level`. **F3 → refuted** (no change) — intentional pedagogical simplification; the message teaches the core contract, optional/structural keys are deliberately omitted (same disposition as Phase-1 F2). *(Pre-existing key-vs-`pipe_code`-field reconciliation smell the reviewer noted in passing is out of scope — orthogonal to signatures, not introduced here.)* All folded into the Phase-2 commit (amended); revised SHA recorded below.
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

- **Phase reached / last green SHA:** Phase 2 complete (additive typeless-signature support mirrored into the spec/authoring layer). Baseline (Phase-1 review diff base) = `04434f78586b328e080fd76b50bf46b00e0b6765`. Phase-1 commit = `e864b82486f00502206c6aa11b609b5256392e30`. Phase-2 commit SHA = `b52b4e8df5a21c2d521d59bd1a08b1d65e028f28` (amended in-place after the Checkpoint-2 review to fold F1/F2 fixes).
- **What changed and where the seam lives (Phase 2, spec layer):**
  - **Shared normalizer.** The Phase-1 per-section logic is now a single module-level free function `normalize_typeless_signature_section(pipe_code, *, pipe_section, allowed_keys=SIGNATURE_ONLY_KEYS)` in `pipelex/core/pipes/pipe_blueprint.py` (next to `SIGNATURE_ONLY_KEYS`). Both layers call it: `PipelexBundleBlueprint.validate_pipe_keys` (blueprint) and the new `PipelexBundleSpec.validate_pipe_keys` (spec). This makes the teaching message — whose exact wording the categorizer's `_MISSING_PIPE_TYPE_MARKER` keys off — truly single-source. The blueprint's old `_normalize_typeless_signature` classmethod was deleted.
  - **Spec dispatch site.** `PipelexBundleSpec.pipe: dict[str, PipeSpecUnion]` (`pipelex/builder/bundle_spec.py`) gained a `@field_validator("pipe", mode="before")` that is a **full** mirror of the blueprint's: it rejects a non-snake_case dict key (`is_pipe_code_valid`) up front, then normalizes each section (typeless contract-only → inject `type = "PipeSignature"` → routes to `PipeSignatureSpec`; typeless + stray field → teaching error; typed section / already-built spec instance → untouched).
  - **Key-set difference.** Spec sections carry `pipe_code` as a field (blueprint uses the dict key) and have **no** `source` field, so the spec allowlist is `SIGNATURE_ONLY_SPEC_KEYS = (SIGNATURE_ONLY_KEYS - {"source"}) | {"pipe_code"}` (defined in `bundle_spec.py`) — it reflects the spec's real field surface, not the blueprint's. *(Both the `-source` and the up-front key check came out of the Checkpoint-2 review — F1/F2.)*
  - **No spec-layer JSON schema.** Confirmed the only committed schema is blueprint-derived (`derived/mthds_schema.json`); nothing to regenerate for the spec layer. (See Phase-2 checklist for the full note.)
- **Phase-1 seam recap (unchanged):** blueprint choke point `PipelexBundleBlueprint.validate_pipe_keys`; `SIGNATURE_ONLY_KEYS` = `{description, inputs, output, signature_for, source}`; error surfacing via `PipeValidationErrorType.MISSING_PIPE_TYPE` + `_categorize_missing_pipe_type_error`; schema arm keeps `type` optional (`_require_type_on_pipe_definitions` skips the signature arm) — Phase 3 removes `type` from the arm (breaking) + migrates fixtures in the same commit.
- **What is verified (tests/gates run):** `make agent-check` fully green (ruff/plxt/pyright-0/mypy-0/keyword-only). Targeted suite (all `tests/unit|integration/pipelex/builder` + `core` + `integration/pipes`) green. Full `make agent-test` green (exit 0, "All tests passed"). New Phase-2 tests: `tests/unit/pipelex/builder/test_bundle_spec_typeless_signature.py`.
- **Invariants confirmed untouched:** reconciliation keys off `is_signature`; `PipeSignature` stays a valid internal discriminator; Phase-1 blueprint behavior byte-for-byte identical (shared-helper refactor is a pure extraction — same message, same logic, verified by the full suite).
- **Open threads / review findings deferred:**
  - Phase-1 deferred item still open in `wip/pipe-signature-not-a-type.md` → "Deferred follow-ups": categorizing the bare pydantic residual for a typeless section missing a required contract field (pre-existing general gap; safety invariant guarded by a test).
  - **Phase-3 gap (new):** once the explicit `type = "PipeSignature"` is rejected, the agent-CLI single-pipe `pipe` command has no way to author a signature (can't pass the tag; errors on absent type). Decide in Phase 3: route typeless → `PipeSignatureSpec` in `pipe_cmd.py`/`parse_pipe_spec`, or make signatures bundle-only. See the Phase-2 checklist note.
- **Exact next action:** Checkpoint-2 cold `/code-review` fan-out on the Phase-2 commit diff (fresh Sonnet-5, no inherited context), triage findings in TODOS, then Phase 3 (the breaking phase: reject the explicit tag, migrate the 8 fixtures, reword rendering, docs, changelog).
