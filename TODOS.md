# Implementation plan — PipeSignature is not a type

**Branch:** `feature/PipeSignature-not-a-type`
**Design doc:** [`wip/pipe-signature-not-a-type.md`](wip/pipe-signature-not-a-type.md) — read this first for the *why*.
**Status:** Phase 3 complete (code + tests + docs green) · pending Checkpoint-3 cold review + commit SHA · this is the final phase

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

- [x] Blueprint before-validator: `type = "PipeSignature"` written explicitly ⇒ **migration error** (D3). Implemented in the **shared** `normalize_typeless_signature_section` (`pipe_blueprint.py`) via `explicit_signature_tag_migration_message(pipe_code)` — so blueprint AND spec layers reject it from one source. Message: "Pipe `<code>` sets `type = "PipeSignature"`, which is no longer a pipe type. Delete the `type` line — a pipe with no `type` and no implementation is a signature (contract only)."
- [x] Spec before-validator: same rejection (shared helper — free).
- [x] **Round-trip safety (new, load-bearing):** `PipeSignatureBlueprint.type` now `Field(exclude=True)` so a signature never serializes its tag. This keeps the `bundle_elaborator.py:94` dump→revalidate round-trip typeless (re-injected), while a **user-written** tag still reaches the validator and is rejected. Verified: signature dump has no `type`, round-trip routes to `PipeSignatureBlueprint`, explicit tag rejected, typeless still routes. (No direct single-pipe `PipeBlueprintUnion` validation exists — all pipe-dict validation flows through `validate_pipe_keys`, which re-injects.)
- [x] **Migration error categorized** → `UNKNOWN_PIPE_TYPE` (a *declared-but-invalid* type — an explicit `type = "PipeSignature"` DID declare a type; it is just no longer valid). Deliberately **not** `MISSING_PIPE_TYPE`, which the enum documents as the *no-type-declared* case — that stays reserved for the typeless-with-stray-field teaching error. The two markers map to the two distinct categories; pipe-code recovered from the shared ``Pipe `<code>``` prefix. *(This split corrected a first-pass mislabel — Louis flagged that a written tag can't be "missing.")*
- [x] **Single-pipe authoring (Phase-2 gap — decision: typeless→signature, Louis chose uniform):** `parse_pipe_spec(pipe_type: str | None)` now routes a typeless spec to `PipeSignatureSpec` and rejects `pipe_type="PipeSignature"` with the migration error; `pipe_cmd.py` allows absent `--type`; `pipe_type_to_spec_class` no longer lists `PipeSignature` (not a selectable type); both TOML renderers (`pipe_ops.pipe_spec_to_toml` **and** `pipe_cmd._pipe_spec_to_toml`) omit the `type` line for a signature.
- [x] Schema generator: `_normalize_type_on_pipe_definitions` (renamed from `_require_type_...`) now **removes `type` from the signature arm entirely** — an explicit tag fails the schema as an extra property under `additionalProperties: false`. Regenerated `derived/mthds_schema.json` (42 defs). Verified against the Draft-4 validator: typeless contract ✓, typeless+stray ✗, explicit tag ✗, concrete ✓, typo'd type ✗. `plxt-lint` passes over the migrated typeless fixtures.
- [x] Migrate the 8 bundle fixtures — `type = "PipeSignature"` line deleted from each (9 lines total; `write_research_brief.mthds` had 2). They are now the typeless regression corpus. Comments referencing the *concept* `PipeSignature` left intact (still accurate).
- [x] `pipe_signature_spec.py` `rendered_pretty`: drops the `Type: PipeSignature (...)` line → "Signature (contract only)". `pipe_category` field retained (taxonomy-refactor scope decision) but comment updated (no longer surfaced).
- [x] Tests: migration error asserted at blueprint, spec, and single-pipe layers; categorizer → `MISSING_PIPE_TYPE` (new `test_explicit_signature_tag_is_a_categorized_blueprint_item`); typeless single-pipe → signature + no-type TOML (both renderers); schema `test_explicit_signature_tag_is_rejected` + coverage-guard fixed for the typeless arm; all Phase-1/2 "explicit tag still accepted" guard tests **flipped** to rejection; inline-TOML test bundles migrated to typeless.
- [x] Docs — taught "omit the type" and removed the idiom **only where it appeared**: `signature-pipes.md` (Parameters table drops the `type` row + teaching lead-in; 3 examples de-tagged; "Replacing a signature" reworded), `index.md` (typeless framing), `pipelex/cli/agent_cli/CLAUDE.md` (`pipe` row). **The other plan-listed docs needed NO change** — `validate.md`, `agent-cli.md`, the error pages, and `error-model.md` reference the *concept* `PipeSignature` / `--allow-signatures` / `pending_signatures` / the runtime error, none of which teach the `type =` idiom (avoided gratuitous churn).
- [x] CHANGELOG.md — added `[Unreleased]` section (there was none) with the **breaking** entry + the MTHDS-JSON-Schema shape-change note (downstream copies re-sync gated on release).
- [x] `make agent-check` green (ruff/plxt/pyright-0/mypy-0/keyword-only) **and** full `make agent-test` green ("All tests passed").

### ⛔ CHECKPOINT 3 — STOP (final)

- [x] Commit the phase. Record SHA: `702f2eff5` (may be amended if the cold review lands fixes).
- [x] Update the **Cold-start snapshot** below to the finished state.
- [x] **Fan out** a fresh Sonnet-5 `/code-review` sub-agent on this commit's diff (fresh, no inherited context; 10 finder angles + empirical REPL checks of the round-trip and Draft-4 schema). Triage:
  - **Angles verified clean:** the explicit-tag round-trip false-positive (traced every dump→revalidate; only `bundle_elaborator.py:94` exists, and the `exclude=True` keeps it typeless) and the Draft-4 `oneOf` disambiguation (ran the real generated schema through `jsonschema.Draft4Validator`). No bug in either — corroborates our own checks.
  - **F1 (major) — categorizer mislabel.** Explicit `type = "PipeSignature"` was bucketed `MISSING_PIPE_TYPE`, but a type *was* declared → should be `UNKNOWN_PIPE_TYPE` (per the enum's own docstring + the sibling `union_tag_invalid` branch that already buckets a typo'd type there). **Already caught by Louis independently and fixed** before the review returned → split `_categorize_typeless_pipe_error`: no-type→`MISSING_PIPE_TYPE`, retired-tag→`UNKNOWN_PIPE_TYPE`; test asserts the new type *and* that it is not also `MISSING_PIPE_TYPE`.
  - **F2 (minor) — renderer drift.** `pipe_ops.add_type_specific_fields` never emitted `signature_for` for a signature, while `pipe_cmd._add_type_specific_fields` does — silent loss of the hint through `pipe_ops.pipe_spec_to_toml` (pre-existing; that fn has no in-repo prod caller, only tests). **Fixed** — added the mirroring `PipeSignatureSpec` branch so the two renderers stay faithful copies; new `test_signature_toml_preserves_signature_for_hint` guards it.
  - No other correctness issues; reviewer confirmed the shared-helper design and the two before-validators are sound faithful mirrors.
- [x] **Gated cross-repo follow-up recorded:** the MTHDS JSON Schema copies in `mthds`, `vscode-pipelex`, `mthds-ui` now drift — the signature arm no longer carries a `type` property (an explicit `type = "PipeSignature"` fails those schemas too). Propagate via the `mthds-schema-sync` skill from the workspace root, **gated on the released pipelex version** — NOT on this branch. Flagged in the CHANGELOG `[Unreleased]` entry.
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

- **Phase reached / last green SHA:** **Phase 3 complete** — the breaking cleanup is done, the feature is fully landed (code + tests + docs green). Baseline = `04434f78586b328e080fd76b50bf46b00e0b6765`. Phase-1 = `e864b82486f00502206c6aa11b609b5256392e30`. Phase-2 = `b52b4e8df5a21c2d521d59bd1a08b1d65e028f28`. Phase-3 commit SHA = _pending commit (recorded at Checkpoint 3 below)_.
- **What changed and where the seam lives (Phase 3, breaking):**
  - **Rejection is single-source.** `normalize_typeless_signature_section` (`pipe_blueprint.py`) now raises `explicit_signature_tag_migration_message(pipe_code)` when a raw dict names `type = "PipeSignature"`. Both `PipelexBundleBlueprint.validate_pipe_keys` and `PipelexBundleSpec.validate_pipe_keys` inherit it. `parse_pipe_spec` (single-pipe) rejects `pipe_type="PipeSignature"` with the same message-builder.
  - **Serialization invariant (the subtle bit).** `PipeSignatureBlueprint.type` is now `Field(exclude=True)`. A signature never serializes its tag, so (a) `.mthds` export stays typeless and (b) the `bundle_elaborator.py:94` dump→revalidate round-trip yields a typeless section that `validate_pipe_keys` re-injects — the tag only appears in a raw section when a **user** wrote it, which is exactly what we reject. No false positives.
  - **Schema.** `_normalize_type_on_pipe_definitions` deletes `type` from the signature arm (was: left optional). Explicit tag now fails the schema (extra property under `additionalProperties: false`). `derived/mthds_schema.json` regenerated.
  - **Single-pipe authoring (Louis' decision: uniform typeless→signature).** `parse_pipe_spec(pipe_type: str | None)`; `pipe_cmd.py` allows absent `--type`; `PipeSignature` dropped from `pipe_type_to_spec_class`; both TOML renderers omit the `type` line for a signature.
  - **Categorizer.** Migration error → `UNKNOWN_PIPE_TYPE` (a declared-but-invalid type; distinct from the typeless-only `MISSING_PIPE_TYPE`). Second marker `_EXPLICIT_SIGNATURE_TAG_MARKER`; pipe-code from the shared ``Pipe `<code>``` prefix.
- **What is verified (tests/gates run):** `make agent-check` fully green (ruff/plxt/pyright-0/mypy-0/keyword-only; schema regenerated + `plxt-lint` clean over the migrated typeless fixtures). Targeted builder/language/signature/libraries/cli + pipeline/cli/e2e suites green. Full `make agent-test` green ("All tests passed").
- **Invariants confirmed untouched:** reconciliation keys off `is_signature`; `PipeSignature` stays a valid **internal** discriminator (injected value still passes `validate_pipe_type` — `valid_pipe_type_tags()` still lists it); strict/`--allow-signatures` validation semantics unchanged.
- **Open threads / review findings deferred (both in `wip/pipe-signature-not-a-type.md` → "Deferred follow-ups"):**
  1. Categorizing the bare pydantic residual for a typeless section missing a *required* contract field (pre-existing general gap; safety invariant guarded by a test).
  2. **New (Phase-3 finding):** spec-layer `PipeSpec.inputs` is **required**, unlike the optional blueprint `inputs` — so a no-inputs signature is authorable at the blueprint/`.mthds` level but not via the spec/single-pipe path. Pre-existing, orthogonal to the tag removal; fixing it (make spec `inputs` optional) touches every spec — deferred.
- **Exact next action:** Checkpoint-3 cold `/code-review` fan-out on the Phase-3 commit diff (fresh Sonnet-5, no inherited context), triage findings, record the cross-repo schema-sync follow-up, hand back to Louis for merge decision. **This is the final phase — nothing pushed.**
