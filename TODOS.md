# PR guide — additive multi-file MTHDS libraries (recursive design)

> **For reviewers.** This branch (`feature/Support-recursive-design`) makes a same-domain `.mthds` library buildable as **separate, additive files** instead of one monolithic file. That unblocks **parallel, top-down method construction**: a header file forward-declares the pipes (and the concepts they need), and definition files fill them in independently — no in-place overwrites, no transient collisions. This document describes *what changed and why* so the diff can be reviewed against intent.

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

## Test coverage (what proves it)

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

---

## Downstream (separate effort, NOT in this PR)

The pipelex runtime support is complete here. The recursive **orchestrator** (`mthds-vibe`) + **worker** (`mthds-signature-expander`) + the `--allow-signatures` hook change live in the sibling `mthds-plugins` repo, prescribed by its `wip/recursive/design.md` (flipped to the additive model). Those artifacts don't exist yet; building them is a fresh effort and depends on the pipelex release carrying this branch.

---

## CHANGELOG (under `[Unreleased]`)

The `[Unreleased]` entry in `CHANGELOG.md` covers the additive multi-file construction (reconciliation, cross-file concept resolution, domain-metadata merge, `pending_signatures`).
