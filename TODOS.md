# PR guide — additive multi-file MTHDS libraries (recursive design) + canonical MTHDS-protocol validate surface

> **For reviewers.** This branch (`feature/Support-recursive-design`) carries two related bodies of work, in landing order:
>
> 1. **Additive multi-file libraries** (Part I below): a same-domain `.mthds` library becomes buildable as **separate, additive files** instead of one monolithic file. That unblocks **parallel, top-down method construction**: a header file forward-declares the pipes (and the concepts they need), and definition files fill them in independently — no in-place overwrites, no transient collisions.
> 2. **Canonical MTHDS-protocol validate surface** (Part II below): the runnability verdict from Part I is promoted onto the protocol level, and `PipelexMTHDSProtocol.validate`/`models` are reworked to produce ONE canonical, typed artifact shape that the hosted API (`pipelex-api`) and the Temporal worker arm reuse instead of re-implementing. Spec: workspace `docs/specs/pipelex-mthds-protocol.md`; plan + decision register: workspace `wip/mthds-protocol-surface-alignment.md` (decisions D1–D14).
>
> This document describes *what changed and why* so the diff can be reviewed against intent.

---

# Part I — additive multi-file MTHDS libraries

## What "additive" means

A library author can split a domain across files:

- a **root / header** file declares the domain header and forward-declares pipes as `PipeSignature` (a "header" with explicit `inputs`/`output` but no body), plus the concepts those contracts reference;
- **definition** files supply the concrete pipes (and may declare more concepts), referencing sibling concepts by bare code.

Loading the whole set must produce the same library no matter the file order, with no spurious duplicate/undeclared errors. Three merge-time rules + one validate-surface addition make that work.

---

## The four changes

### 1. Pipe signature ↔ concrete reconciliation

When two declarations of the same `pipe_ref` collide in the library merge:

| existing → incoming | result |
| --- | --- |
| concrete + concrete | **error** — genuine duplicate (unchanged) |
| signature + concrete | **concrete wins** (definition satisfies the header) |
| concrete + signature | **concrete wins** (header ignored) |
| signature + signature | keep one via a deterministic, load-order-independent tie-break |

Whenever at least one side is a signature, the two contracts **must agree**. Agreement is **normalized concept identity**, not raw-string equality: a header's bare `Brief` and a definition's `thisdomain.Brief` denote the same concept, as do `Text` and `native.Text`; structural multiplicity (`[]` vs `[1]`) stays distinct. Mismatched contracts are an error. Input *names* must match exactly (they are variable names, not concepts).

Conceptually this is **a contract fulfilled by an implementation**, not a swap between two pipe *types*: after the taxonomy eviction (below), `PipeSignature` is not a `PipeType`, so reconciliation keys off `blueprint.is_signature` (a class fact) — never an enum tag. `contracts_match()` is unchanged.

- `pipelex/libraries/library_crate_factory.py` — `_reconcile_pipe_collision` + the merge loop. Operates on a small `PipeDeclaration` (blueprint + source) record.
- `pipelex/libraries/contract_match.py` — **NEW.** `contracts_match()` + `_canonical_concept_spec()`: normalization-for-identity only (NOT refinement substitutability — that stays the dry-run's job).
- `pipelex/libraries/collision_messages.py` — **NEW.** `duplicate_ref_msg()`: shared same-file vs cross-file message for duplicate concept/pipe.

### 2. Cross-file concept resolution

Concept references resolve against the **merged library** instead of per file, so a concept declared once is referenceable by bare code from sibling files of the same domain — within one load batch **or across separate batches** (e.g. a concept loaded via a `-L` directory, then a root file referencing it loaded separately). A concept declared twice still raises `ConceptLibraryError`.

The old per-file gate (`validate_local_concept_references` in `PipelexBundleBlueprint`) could not tell a typo from a valid cross-file ref, so it was removed; the check is reproduced where all declarations *and* the live library are visible — the loader.

- `pipelex/core/bundles/pipelex_bundle_blueprint.py` — removed the per-file same-domain concept gate (and the symmetric per-file *pipe* gate, which was the existing asymmetry — bare pipe refs were already deferred to library-level resolution). Reference **collectors** stay; `collect_concept_references()` is now public, mirroring `collect_pipe_references()`.
- `pipelex/libraries/concept_reference_validation.py` — **NEW.** Pure `validate_concept_references_in_blueprints(blueprints, already_loaded_concept_refs=None)`: membership against `batch ∪ already-loaded ∪ native`; the error message lists only the batch's own declarations; every unresolved ref is accumulated and reported together.
- `pipelex/libraries/library_manager.py` — calls the validator from `load_from_blueprints` *and* `load_concepts_only_from_blueprints` (batch ∪ live-library concepts). `load_from_crate` derives its pipe-factory bare-concept guard (`domain_concept_codes`) from the **live library**, not just the crate — the pipe-factory counterpart to the cross-batch check, so bare cross-batch refs resolve end-to-end (relaxing-only; no-op for self-contained crates incl. the Temporal path). Dependency loading now routes multi-file packages through `LibraryCrateFactory.make_from_blueprints`, so a dependency package can itself be additive (signature + concrete).

### 3. Order-independent domain-metadata merge

Domain `description` / `system_prompt` merge order-independently across same-domain files. A membership-only sibling that declares only `domain = "..."` omits these — an omission contributes **no opinion** (it neither overrides nor warns), so whichever file declares the value wins regardless of filesystem load order. Two files declaring *different* non-empty values keep the first and **warn** (a real double-declaration). Same value → no warning.

- `pipelex/libraries/domain/domain_metadata_merge.py` — **NEW.** `merge_domain_metadata_field()`, the single shared rule.
- `pipelex/libraries/library_crate_factory.py` and `pipelex/libraries/domain/domain_library.py` — both wired to the shared helper (crate-merge path + runtime `DomainLibrary.add_domains`).

### 4. `pending_signatures` on a successful validate

A successful `validate bundle` (notably `--allow-signatures`) reports the library-wide set of pipes still declared as `PipeSignature` — so a top-down build sees exactly what remains to define.

- `pipelex/pipeline/validate_bundle.py` — `build_pending_signatures()` + a `pending_signatures` field on the result.
- `pipelex/builder/operations/validate_ops.py`, `pipelex/cli/agent_cli/commands/validate/_validate_core.py` — `pending_signatures` in the JSON envelope.
- `pipelex/cli/agent_cli/commands/validate/_output_helpers.py` — a "Pending signatures" markdown section.

---

## Error surfacing

`ConceptLibraryError` / `PipeLibraryError` were reparented from `PipelexError` directly to `LibraryError`, so a single `except LibraryError` arm in `_translate_to_validate_bundle_error` turns an unresolved cross-file ref (and the pre-existing raw duplicate-concept/pipe errors) into a clean structured `ValidateBundleError` instead of a raw traceback. `PipeNotFoundError` (also a `PipeLibraryError`) keeps its dedicated `--pipe`-slice handler via an `except PipeNotFoundError: raise` placed *before* the `LibraryError` arm. `_load_mthds_files_into_library` gained a surgical `(ConceptLibraryError, PipeLibraryError)` file-context arm (kept narrow so `LibraryLoadingError`'s structured fields survive).

- `pipelex/libraries/concept/exceptions.py`, `pipelex/libraries/pipe/exceptions.py` — reparenting (class names / `type_uri` / doc slugs unchanged).
- `pipelex/pipeline/validate_bundle.py` — the translate arms.

---

## Part I test coverage (what proves it)

- `tests/unit/pipelex/libraries/test_library_crate.py` (+ `test_library_crate_data.py`) — signature/concrete reconciliation matrix (both orders, signature+signature match/mismatch, contract mismatch).
- `tests/unit/pipelex/libraries/test_concept_reference_validation.py` — the pure validator, incl. the cross-batch (`already_loaded_concept_refs`) case and message format.
- `tests/unit/pipelex/libraries/test_domain_library.py` — domain-metadata merge matrix (both orders, same-value, conflict; `description` + `system_prompt`; warnings asserted via `caplog`).
- `tests/unit/pipelex/libraries/test_dependency_multi_file_reconciliation.py` — additive (signature + concrete) **dependency** packages.
- `tests/unit/pipelex/cli/agent_cli/test_validate_output_helpers.py` — the "Pending signatures" markdown section.
- `tests/unit/pipelex/core/.../test_pipelex_bundle_blueprint_concept_construction.py` — per-file construction smoke tests (replaces the relocated per-file validation tests).
- `tests/integration/pipelex/libraries/test_additive_multi_file_library.py` — end-to-end `validate bundle <root> -L <dir>`: lenient passes with the signature, strict passes once the definition is present, concrete wins, cross-batch via `-L`, undeclared → clean `ValidateBundleError`.
- `tests/integration/pipelex/libraries/test_cross_file_concept_references.py` — cross-batch + single-batch bare-ref resolve; undeclared → `ConceptLibraryError`.
- `tests/integration/pipelex/pipeline/test_load_concepts_only.py` — concepts-only path incl. dangling `concept_ref`/`item_concept_ref` rejection and the **sibling cross-reference order-independence** regression test.

Verification: `make agent-check` clean (ruff, plxt, pyright 0 errors, mypy success); `make agent-test` full suite green.

---

## Key design decisions

- **Normalized identity at merge, substitutability at dry-run.** The merge runs at blueprint level (raw strings, before concepts resolve), so `contracts_match` normalizes *identity* (bare ≡ qualified, native spelling, multiplicity-as-text). Covariant-output / contravariant-input substitutability is deferred to the dry-run, which re-validates the parent against the concrete's real contract.
- **Concept refs validate at the loader, not per file.** The one place holding both the raw blueprints (for messages + sources) and the live library (for already-loaded concepts). This makes `get_crate` and per-batch `load_from_blueprints` agree by construction.
- **Reparent then catch once.** One `except LibraryError` arm covers the new undeclared-ref error and the pre-existing raw duplicate errors uniformly, rather than scattering catches.
- **Per-file relaxation scope: concepts (and the already-deferred bare pipe refs).** Same-domain *qualified* cross-file refs are still not emitted by the recursive flow; not in scope.
- **Exact-match contract requires explicit `inputs`/`output` on both header and definition.** `PipeLLM` does not infer `inputs` from prompt sigils, so a header with explicit `inputs` and a definition that omits them would mismatch — the additive flow must emit both explicitly (pinned by a test).

See `wip/recursivity/` for the deeper records:

- [`recursive-followups.md`](wip/recursivity/recursive-followups.md) — `pending_signatures` + normalized contract conformance (both shipped).
- [`domain-metadata-merge.md`](wip/recursivity/domain-metadata-merge.md) — the metadata-merge rule (shipped).

---

## Deferred (intentionally out of scope)

- **Partial-hierarchical same-domain typo skipped as external.** A ref like `legal.Foo` when the bundle domain is `legal.contracts` is treated as external (`QualifiedRef.is_external_to` uses exact-equality) and skipped, so the typo only fails later at resolution. Pre-existing — identical in the old per-file validator; fixing needs an ancestor/prefix notion of domain. Tracked in `wip/recursivity/`.
- **P3 polish from the pre-landing `/review`** (docstring accuracy, an advisory-description silent-drop note, one low-confidence test-coverage gap) — none are bugs; recorded in [`review-followups.md`](wip/recursivity/review-followups.md).

---

---

# Part II — canonical MTHDS-protocol validate surface

The MTHDS Protocol (five routes: `execute`/`start`/`validate`/`models`/`version`) had **diverged between the local implementation and the hosted API**: same protocol operation, unrelated artifact shapes (the hosted `/validate` never called `PipelexMTHDSProtocol.validate` at all). This part makes pipelex the single owner of the canonical artifact shapes; the hosted `pipelex-api` rewires its routes through them in a companion branch (`pipelex-api@feature/Recursivity-and-protocols`). Principle: **backend overrides change backend, never shape; routes are thin wrappers adding wire-only extras** — exactly how `/execute`/`/start` already worked.

## The canonical validation report

`PipelexValidationReport` moved to its own module `pipelex/pipeline/validation_report.py` and is now fully **typed** (no `Any` dumps — the typed schemas flow into pipelex-api's committed OpenAPI artifact):

- `bundle_blueprint: PipelexBundleBlueprint` — the batch's PRIMARY blueprint (first declaring `main_pipe`, else first). Renamed from the hosted side's `pipelex_bundle_blueprint`: blueprints are MTHDS-language artifacts, so no `pipelex_` prefix inside an already-Pipelex-branded envelope (the brand-boundaries principle in the workspace `CLAUDE.md`).
- `pipe_structures: dict[str, PipeIOContract]` — per-pipe IO contracts keyed by **namespaced `pipe_ref`** (`domain.code`), never bare code. The builder (`build_pipe_structures`) is **ported from pipelex-api's route-local `_build_pipe_structures`** — it is runtime logic over `PipeAbstract`/`StuffSpec` the API repo should never have owned. New module `pipelex/pipeline/pipe_structures.py` (`PipeIOContract`/`PipeInputContract`/`PipeOutputContract`, `IOMultiplicity = single|variable`); JSON-Schema rendering memoized per `(concept_ref, is_multiple)` within a call (deliberately not cross-call — stale-class hazard). A pydantic schema-generation failure raises a structured `PipeStructuresError` with pipe/input context (it must not cross the Temporal boundary as a raw retryable third-party error).
- `graph_spec: GraphSpec | None` — **best-effort real graph on the local protocol too** (was always `None`): one shared `best_effort_graph_spec(pipe_ref, *, library_id, log_context)` in `pipelex/pipe_run/dry_run_in_process.py` runs `dry_run_pipe_in_process` against the **already-open validation library, before the lifecycle teardown** — the same single-load pattern as the Temporal activity, used by both backends. Degrade catch `(PipelexError, ValidationError, FactoryException)` → `None` with a warning.
- `validated_pipes: list[ValidatedPipeEntry]` — per-pipe sweep outcomes, same entries as the agent-CLI envelope. **`ValidatedPipeEntry` key renamed `pipe_code` → `pipe_ref`** (the value always WAS the namespaced ref — a documented misnomer, fixed before the key gets canonized onto a protocol surface). `typing_extensions.TypedDict`, not `typing.TypedDict` (pydantic rejects the latter as a model field on Python < 3.12).
- `pending_signatures: list[str]` + `is_runnable: bool` — the Part I runnability verdict, promoted onto the protocol report.

One selection rule, one constructor, every backend: `select_primary_blueprint` (in `pipe_structures.py`; also folds the previously-duplicated first-declaring-main_pipe loops in `execution_seams.py`, `dry_run_pipeline.py`, `inputs_ops.py`) and `build_validation_report(...)` (in `validation_report.py`) are the only way reports are assembled — `PipelexMTHDSProtocol.validate` locally, `ApiRunner.validate` hosted (companion branch).

- `pipelex/pipeline/runner.py` — `validate` reworked: artifacts built inside the library window (the validation library id captured ONCE after `validate_bundle`; graph arm + `finally` target the same library; a teardown raise is suppressed while a body error propagates, mirroring the Temporal activity). Return annotations narrowed to the concrete `PipelexValidationReport`/`PipelexModelDeck` so typed consumers (ApiRunner, routes) get typed access. An empty `mthds_contents` list is a structured `ValidateBundleError`, not a raw `IndexError`.

## Temporal wire (`DryValidateResult`)

The worker computes everything with its already-loaded library and ships it across the boundary, so the API side never re-acquires a library: `DryValidateResult` gains `pending_signatures` and `pipe_structures` as **required** wire fields (version-skewed workers fail loudly instead of silently yielding `is_runnable=True`). `PipeStructuresError` is non-retryable at the `wf_dry_validate` tier alongside `ValidateBundleError`. Integration test pins both fields crossing the in-process Temporal boundary. Size sanity-checked on a large structured bundle: `pipe_structures` is an order of magnitude smaller than the `graph_spec` that already crossed the wire; the payload cap is far away.

## Model deck

`PipelexModelDeck.aliases`/`waterfalls` are now **keyed by category** (`{category: {alias: model}}`): the old flat maps were built by `update()`-ing per-category maps and silently dropped cross-category alias collisions (e.g. `default-small`/`best-gpt` exist per category — proven against captured baselines). The protocol's flat `models` list is unchanged.

## Module moves (import-cycle breaks, mechanical)

- `dry_run_pipe_in_process` → NEW `pipelex/pipe_run/dry_run_in_process.py` (its old home `dry_run_pipeline.py` imports the runner; the runner importing the graph arm from it would close a cycle).
- `dry_run_pipeline` → `pipelex/pipeline/dry_run_pipeline.py` (layering follow-up; importers + docs re-pointed).
- `select_primary_blueprint` lives in `pipe_structures.py`, NOT `validate_bundle.py` — importing from `validate_bundle` in `execution_seams` closed a cycle through `bundle_validator`.
- `MTHDS_PROTOCOL_VERSION` deleted: `version()` reports the SDK's `PROTOCOL_VERSION` directly ("single source of truth … runners do not get to override it"); the temporary re-export staged for pipelex-api's import was removed once the companion branch imports the SDK constant.

## Part II test coverage

- `tests/unit/pipelex/pipeline/test_pipe_structures.py` — the D6 builder: `PipeSignature` pipes in lenient batches, multiplicity entry shapes, memoization, the `PipeStructuresError` wrap; `select_primary_blueprint` first-declaring / none / multiple.
- `tests/integration/pipelex/pipeline/test_protocol_validate.py` — the canonical report shape + lifecycle: graph populated on main-pipe bundles, graph-failure-mid-window degrades to `None` while restore/teardown holds (asserted WITHOUT mocks on the real-graph case), strict-raise, empty-contents guard.
- `tests/integration/pipelex/temporal/` — both new `DryValidateResult` fields cross the boundary.
- Downstream proof (not in this repo): pipelex-api's suite runs against this branch via an editable pin — local↔hosted byte-identity per fixture class is pinned by its `tests/unit/test_protocol_parity.py`; the conformance repo pins the agent-CLI envelope against workspace `docs/specs/pipelex-mthds-protocol.md`.

---

## Downstream (separate effort, NOT in this PR)

The pipelex runtime support is complete here. The recursive **orchestrator** (`mthds-vibe`) + **worker** (`mthds-signature-expander`) + the `--allow-signatures` hook change live in the sibling `mthds-plugins` repo, prescribed by its `wip/recursive/design.md` (flipped to the additive model). Those artifacts don't exist yet; building them is a fresh effort and depends on the pipelex release carrying this branch.

On the protocol side (Part II), the companion consumers ship after this branch releases: `pipelex-api@feature/Recursivity-and-protocols` (routes through the canonical report; restores its PyPI pin at the release carrying this branch), `pipelex-app@feature/protocol-alignment` (renamed wire field + `pipe_ref` lookups), `conformance@feature/Pending-signatures` (envelope conformance tests — red against `dev` pipelex until this merges).

---

## CHANGELOG (under `[Unreleased]`)

The `[Unreleased]` entry in `CHANGELOG.md` covers the additive multi-file construction (reconciliation, cross-file concept resolution, domain-metadata merge, `pending_signatures`), the `PipeSignature` taxonomy eviction (removed `PipeType`/`PipeCategory.PIPE_SIGNATURE`), and the Part II protocol rework (canonical typed report, `pipe_ref` re-keying + D7 rename, graph arm, Temporal wire fields, category-keyed deck extensions, module moves). It also corrects the v0.33.0 entry's `protocol_version` claim (0.1.0 → 0.6.0, a factual error).

---

## Pre-merge design change — DONE

Review flagged that `PipeSignature` should not be a peer pipe type — it's a contract substrate of `PipeAbstract`, not a sibling of `PipeLLM`/`PipeSequence`. **Landed:** `PipeSignature` is evicted from the executable taxonomy. `PipeType.PIPE_SIGNATURE` and `PipeCategory.PIPE_SIGNATURE` are removed; `is_signature` is now a class fact (base returns `False`, `PipeSignature` / `PipeSignatureBlueprint` override to `True`) instead of an enum read; a signature carries `type = "PipeSignature"` with `pipe_category = None`, admitted by the shared validators via a `PIPE_SIGNATURE_TYPE_TAG` allowlist entry. It stays a `PipeAbstract` subclass (the dry-run shim) and keeps `signature_for` for mthds-plugins (its `reject_signature_for_pipe_signature` guards are gone — the rejection is now structural, since `PipeSignature` is no longer a `PipeType` the field can coerce). As-built plan: [`signature-taxonomy-refactor.md`](wip/recursivity/signature-taxonomy-refactor.md).
