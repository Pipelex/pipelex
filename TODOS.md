# TODOS — Make the additive multi-file library model work end-to-end

Two coupled changes unblock **additive, parallel, top-down method building** (designed in `mthds-plugins/wip/recursive/design.md`):

- **Part A — Pipe reconciliation.** A `PipeSignature` and a concrete pipe with the same code reconcile in the library merge (the concrete wins) instead of raising a duplicate-code error.
- **Part B — Concept references validate at library level.** Cross-file, same-domain concept references resolve against the *merged* library instead of being rejected per-file, so a concept declared once can be referenced from sibling files.

Both are required. Part A alone does **not** unblock the goal: any pipe whose contract uses a non-native concept (the common case) cannot be authored additively, because per-file validation rejects a file that references a same-domain concept declared in a sibling file. Verified end-to-end against the design doc's own `research_brief` example — it does not load today.

---

## 📍 Cold-start status — UPDATE AT EVERY CHECKPOINT

> This block is the single source of truth for resuming in a fresh session. A new agent should read this first. Overwrite it at each checkpoint.

- **Branch:** `feature/Support-recursive-design` (pipelex worktree `_recursive`). Handoff doc lives in sibling repo `mthds-plugins`, branch `feature/Recursive-building`.
- **Plan state:** ✅ **ALL PHASES DONE.** Phase 1 (Part A) `f5fd826f`, Phase 2 (Part B) `d91701f4`, Phase 3 (end-to-end + both folded-in review fixes) `13660d3a` — all **committed**, full `make agent-test` green. Phase 4 (handoff) **done**: `mthds-plugins/wip/recursive/design.md` flipped overwrite-in-place → additive model (**uncommitted in mthds-plugins**, see below).
- **Current phase:** **Feature complete.** The pipelex runtime support (Parts A+B + end-to-end proof) is shipped on this branch; the design handoff (Phase 4) is written. The only remaining work is **downstream in `mthds-plugins`** — building the recursive `mthds-vibe` orchestrator + `mthds-signature-expander` worker + the hook `--allow-signatures` change per `design.md` §7. Those artifacts **do not exist yet** (still the single-pass skill); that is a separate effort, not part of this pipelex feature.
- **Last verified green (Phase 3):**
  - NEW unit `tests/unit/pipelex/libraries/test_concept_reference_validation.py` (renamed from `test_library_crate_concept_references.py`) — targets the pure `validate_concept_references_in_blueprints`; added a cross-batch (`already_loaded_concept_refs`) case. All pass.
  - NEW integration `tests/integration/pipelex/libraries/test_cross_file_concept_references.py` (cross-batch + single-batch bare-ref resolve, undeclared→`ConceptLibraryError`) and `test_additive_multi_file_library.py` (lenient-with-signature, strict-with-definition/concrete-wins, cross-batch via `-L`, undeclared→clean `ValidateBundleError`) — all pass.
  - Targeted regression sweep (unit+integration `libraries/` + `pipeline/` + unit `errors/`) — all pass, incl. error-location + `type_uri` uniqueness (reparenting clean) and reserved-domains `LibraryLoadingError`.
  - **Full `make agent-test` — green ("All tests passed", exit 0).** `make agent-check` — clean (ruff, plxt, pyright 0 errors/0 informations, mypy success).
- **Next concrete action:** (pipelex side already committed.) **Commit the Phase 4 handoff in `mthds-plugins`** (branch `feature/Recursive-building`, working tree = `wip/recursive/design.md` only) — suggested msg: `docs(recursive): flip design to the shipped additive model (header + definition)`. After that this feature is closed; the downstream skill work (design.md §7) is a fresh effort.
- **Phase 3 working tree (now committed in `13660d3a` — precise file list, historical):**
  - `pipelex/libraries/concept_reference_validation.py` — **NEW.** Pure `validate_concept_references_in_blueprints(blueprints, already_loaded_concept_refs=None)`: batch-declared (for the message) + membership against batch ∪ already-loaded ∪ native. Raises `ConceptLibraryError`. **Complete.**
  - `pipelex/libraries/library_crate_factory.py` — removed `_validate_concept_references` + its call; `make_from_blueprints` is now a pure structural merge + fingerprint (dropped `NativeConceptCode`/`QualifiedRef` imports). **Complete.**
  - `pipelex/libraries/library_manager.py` — `load_from_blueprints` now calls `validate_concept_references_in_blueprints` (batch ∪ `library.concept_library.root` keys); `load_from_crate` builds `domain_concept_codes` from the **live library** (not just `crate.concepts`) so the pipe factory's bare same-domain guard is library-aware too; `_load_mthds_files_into_library` gained a surgical `except (ConceptLibraryError, PipeLibraryError)` file-context arm. **Complete.**
  - `pipelex/libraries/concept/exceptions.py` + `pipelex/libraries/pipe/exceptions.py` — `ConceptLibraryError`/`PipeLibraryError` reparented `PipelexError` → `LibraryError`. **Complete.**
  - `pipelex/pipeline/validate_bundle.py` — `_translate_to_validate_bundle_error` gained `except PipeNotFoundError: raise` (pass-through) **then** `except LibraryError` (→ `ValidateBundleError`, forwarding `LibraryLoadingError` structured fields). New imports: `LibraryError`, `LibraryLoadingError`. **Complete.**
  - `tests/unit/pipelex/libraries/test_concept_reference_validation.py` — git-mv rename of the Part B unit module + rewire to the pure fn + cross-batch case. **Complete.**
  - `tests/integration/pipelex/libraries/test_cross_file_concept_references.py`, `tests/integration/pipelex/libraries/test_additive_multi_file_library.py` — **NEW.** **Complete.**
  - `CHANGELOG.md` — added `[Unreleased]` with the Additive multi-file construction entry. **Complete.**
  - `TODOS.md` — this checkpoint update.
- **Decisions/surprises (Phase 3):**
  - **Finding #1 needed a second half.** Moving only the *check* to the loader was a half-fix: the pipe factory's bare same-domain guard (`PipeFactory.make_from_blueprint`, via `load_from_crate`'s `concept_codes_from_the_same_domain`) was ALSO batch-local, so a bare cross-batch ref would pass the check then fail with a different `PipeFactoryError`. Made `load_from_crate` derive `domain_concept_codes` from the live library (relaxing-only; no-op for self-contained crates incl. the Temporal path). Bare cross-batch refs now work end-to-end (proven by integration test). This extends the recorded Finding-#1 decision.
  - **Reparenting regression caught by the full suite.** `PipeNotFoundError` is a `PipeLibraryError` → now a `LibraryError`, so the new `except LibraryError` arm initially swallowed the `--pipe`-slice "pipe not found" error (which has its own handler in `execute_validate`). Fix: `except PipeNotFoundError: raise` placed before the `except LibraryError` arm. (`test_pipe_slice_unknown_pipe_raises_not_found`.)
  - **Pure-fn extraction over a manager method.** The check is a free function in a focused module (`concept_reference_validation.py`), keeping `make_from_blueprints` world-agnostic AND the message-format unit tests fast (no live library); the loader supplies the library's concepts as `already_loaded_concept_refs`. The error *message* lists only the batch's declarations (clean), while *membership* honors already-loaded library concepts.
  - **`_load_mthds_files_into_library` widening kept surgical** (`ConceptLibraryError`/`PipeLibraryError` only, re-raised same-type with file context) rather than `except LibraryError`, to avoid clobbering `LibraryLoadingError`'s structured `blueprint_validation_errors`/`pipe_concept_validation_errors`.
  - **Process note:** the first full run reported "exit 0" because it was piped through `tail` (pipeline exit = `tail`'s). Re-ran `make agent-test` directly so the notification carried `make`'s real exit code.
- **Phase 4 (handoff) — what changed & findings:**
  - Rewrote `mthds-plugins/wip/recursive/design.md` to make the **additive** model primary throughout (TL;DR, §2.1/§2.3/§2.5/§2.6 methodology, §2.7 layout, §3 worked example, §4.1/§4.4/§4.5, §5.2/§5.4 hook nudge, §6 decisions, §7 plan). Retired overwrite-in-place; added the **exact-match contract** rule (explicit identical `inputs`/`output` on header + definition — pipes don't infer inputs from prompt sigils). **No code touched in mthds-plugins.**
  - **Finding:** the mthds-plugins recursive impl is **entirely unstarted** (single-pass `mthds-vibe/SKILL.md.j2`, no `agents/`, no `mthds-signature-expander`, no `PipeSignature`/`--allow-signatures` in templates). So Phase 4 task "adopt additive in orchestrator/worker" became "make `design.md` prescribe additive for them" (§4.4, §4.5, §7 items 3-4) — there is nothing to edit yet.
  - **Version floor:** lenient validation needs pipelex ≥ 0.31.0 (released); the additive model needs Part A+B which are **[Unreleased]** (only this branch) → additive floor = the next pipelex release > 0.31.0. (design.md §6.)
  - **Hook nudge correctness:** under additive, headers persist, so `grep -q '"PipeSignature"'` false-positives — leftover-signature detection must use the validator's reachable-signature report (`{signatures} − {concretes}`). (design.md §5.2/§5.4.)
  - `Page` is a native concept (`NativeConceptCode.PAGE`), so the worked example's `Page[]` needs no declaration (carried over from the original, verified).
- **Open questions blocking progress:** none for the pipelex feature. Downstream-open (tracked in design.md §6): the exact pipelex release carrying Part A+B, and the matching mthds-agent version.
- **Deferred (see "Deferred follow-ups" below):** the concepts-only loader still does not validate undeclared structure `concept_ref`/`item_concept_ref` at construction (narrow, secondary path; recursive flow uses the full load path, fully covered). Finding #4 (the original recorded deferred item). The bare-ref cross-batch limitation is **no longer deferred — it was fixed in this phase.**

---

## 🛑 Checkpoint protocol (run ALL steps at every "MANDATORY STOP" marker)

At each checkpoint the agent **must stop and not continue into the next phase in the same session**. Before stopping:

- [ ] Run `make agent-check` — lint + types must be clean. Fix anything reported.
- [ ] Run the relevant tests (targeted suites during the phase; `make agent-test` for the final checkpoint). Record the actual pass/fail summary in the cold-start block.
- [ ] Tick every completed checkbox in this file; leave partial work as `[ ]` with a one-line note of what remains.
- [ ] Overwrite the **Cold-start status** block above: branch, phase, last-green, exact next action, precise working-tree state (files changed + whether each is complete), decisions/surprises, open questions.
- [ ] If commits are authorized, commit at the checkpoint using the per-checkpoint message below and record the SHA; otherwise list the uncommitted files precisely so the next session can `git diff` to recover context. (Do **not** auto-commit without authorization.)
- [ ] State plainly to the user: what is done, what is verified, what is next.

The point of a checkpoint is a clean cold start: a new session reading the cold-start block + this file should be able to resume with zero lost context.

---

## Progress overview

- [x] **Phase 1 — Part A:** pipe signature/concrete reconciliation → 🛑 **Checkpoint A** ✅
- [x] **Phase 2 — Part B:** concept references validate at library level → 🛑 **Checkpoint B** ✅
- [x] **Phase 3 — End-to-end proof** + full suite + lint → 🛑 **Checkpoint C (UNBLOCK POINT)** ✅
- [x] **Phase 4 — Handoff:** `design.md` flipped to the additive model ✅ — orchestrator/worker/hook still unbuilt; their implementation is mthds-plugins §7 (downstream, separate effort)

---

## Phase 1 — Part A: pipe signature/concrete reconciliation

### Semantics

Reconciliation is **file-agnostic** and order-independent. For a given `pipe_ref` seen more than once:

| existing → incoming | result |
| --- | --- |
| concrete + concrete | **error** (genuine duplicate — unchanged behavior) |
| signature + concrete | **concrete wins** (definition replaces declaration) |
| concrete + signature | **concrete wins** (declaration ignored) |
| signature + signature | keep one (idempotent forward declarations) |

Whenever at least one side is a signature, the two declarations' **contracts must agree** (same `inputs`, same `output`); a mismatch is an error.

### Where

`pipelex/libraries/library_crate_factory.py` — the pipe-merge block (currently lines 94–114). Signature detection: `pipe_blueprint.is_signature` (`pipelex/core/pipes/pipe_blueprint.py:108`). Values are `PipeBlueprintUnion` (already imported); `PipeBlueprint` exposes `inputs: dict[str, str] | None` and `output: str`. No new imports needed.

### Tasks

- [x] Replace the duplicate-detection branch in the pipe loop with a `_reconcile_pipe_collision(...)` call (snippet below).
- [x] Add `_reconcile_pipe_collision` (classmethod), `_contracts_match` (staticmethod), `_duplicate_pipe_msg` (the current same-file vs cross-file messages), and `_contract_mismatch_msg`.
- [x] `_contract_mismatch_msg` must read correctly for **both** signature+concrete and signature+signature (two headers can disagree). Phrase as "declared with mismatched contracts," not "a signature and its implementation."
- [x] Add unit tests + fixtures (see below).
- [x] `make agent-check` clean; libraries targeted suite green.

```python
# Pipes
if blueprint.pipe is not None:
    for pipe_code, pipe_blueprint in blueprint.pipe.items():
        pipe_ref = PipeFactory.make_pipe_ref_with_domain(domain_code=domain_code, pipe_code=pipe_code)
        if pipe_ref in pipes:
            winner = cls._reconcile_pipe_collision(
                pipe_ref=pipe_ref,
                existing=pipes[pipe_ref],
                existing_source=source_map.get(pipe_ref),
                incoming=pipe_blueprint,
                incoming_source=source,
            )
            if winner is pipe_blueprint:
                pipes[pipe_ref] = pipe_blueprint
                if source:
                    source_map[pipe_ref] = source
            # else: existing declaration wins — leave pipes/source_map untouched
            continue
        pipes[pipe_ref] = pipe_blueprint
        if source:
            source_map[pipe_ref] = source
```

```python
@classmethod
def _reconcile_pipe_collision(
    cls,
    pipe_ref: str,
    existing: PipeBlueprintUnion,
    existing_source: str | None,
    incoming: PipeBlueprintUnion,
    incoming_source: str | None,
) -> PipeBlueprintUnion:
    """Resolve two declarations of the same pipe_ref.

    A PipeSignature is a forward declaration ("header"); a concrete pipe is its
    definition. The concrete wins; the contracts must agree whenever a signature
    is involved. Two concrete pipes are a genuine duplicate. Returns the winner.
    """
    same_file = existing_source is not None and existing_source == incoming_source

    # Both concrete -> genuine duplicate (unchanged behavior).
    if not existing.is_signature and not incoming.is_signature:
        raise PipeLibraryError(cls._duplicate_pipe_msg(pipe_ref, existing_source, incoming_source, same_file))

    # At least one is a signature: the declarations' contracts must match.
    if not cls._contracts_match(existing, incoming):
        raise PipeLibraryError(cls._contract_mismatch_msg(pipe_ref, existing, existing_source, incoming, incoming_source))

    # Concrete beats signature; if both are signatures, keep the one already seen.
    return incoming if (existing.is_signature and not incoming.is_signature) else existing


@staticmethod
def _contracts_match(a: PipeBlueprintUnion, b: PipeBlueprintUnion) -> bool:
    """True if two declarations share the same inputs and output (string-level; see Conformance)."""
    return (a.inputs or {}) == (b.inputs or {}) and a.output == b.output
```

### Conformance — exact string match at merge (v1)

The merge runs at *blueprint* level (raw strings, before concepts resolve), so only exact comparison is feasible. Substitutability (covariant output / contravariant inputs / exact multiplicity) is deferred to the dry-run, which re-validates the parent against the concrete's real contract and is refinement-aware. Exact-match can only *reject*, never wrongly accept.

**Verified facts (don't re-investigate):**

- Order-independence holds for the fingerprint: `compute_fingerprint_from_content` sorts keys + `sort_keys=True` (`library_crate.py:49-53`). The winning per-key value is the concrete regardless of load order; dict iteration order may differ but nothing depends on it.
- `PipeLLMBlueprint(prompt="… $doc …")` with `inputs` omitted keeps `inputs=None` — it does **not** infer inputs from prompt sigils. So a header with explicit `inputs` and a definition that omits them would mismatch. The additive flow must emit **explicit, identical `inputs`/`output` on both header and definition** — pin this with a test (below) and document it for the orchestrator in Phase 4.
- `signature_for` is a hint, not enforced against the concrete's real type. Out of scope for v1.

### Phase 1 tests — `tests/unit/pipelex/libraries/test_library_crate.py` (+ fixtures in `test_library_crate_data.py`)

Keep existing `test_pipe_collision_*` (two concretes still raise). Add:

- [x] signature **then** concrete (cross-file) → concrete wins; `crate.pipes[ref].is_signature is False`; `source_map[ref]` is the concrete's file. — `test_signature_then_concrete_concrete_wins`
- [x] concrete **then** signature (reverse order) → concrete wins; same assertions (order-independence). — `test_concrete_then_signature_concrete_wins`
- [x] signature + signature, matching contract → one survives, still a signature. — `test_signature_plus_signature_matching_keeps_one_signature`
- [x] signature + signature, mismatched contract → `PipeLibraryError`. — `test_signature_plus_signature_mismatched_raises`
- [x] signature + concrete, mismatched inputs/output → `PipeLibraryError`. — `test_signature_plus_concrete_mismatched_inputs_raises`
- [x] signature with explicit `inputs` + concrete that **omits** `inputs` → `PipeLibraryError` (pins exact-match; documents the orchestrator requirement). — `test_signature_with_inputs_plus_concrete_without_inputs_raises`
- [x] New fixtures: a `PipeSignatureBlueprint` for an existing concrete code (matching contract), a mismatched-contract concrete, a second signature variant. Built a self-contained `reconcile` domain using native `Text` contracts (sidesteps per-file concept validation still active until Part B), rather than coupling to `SCORING_*`.

### Downstream — confirm only, no change expected

- [x] Signature pre-pass (`pipelex/pipeline/bundle_validator.py::_signature_pre_pass`, `pipelex/pipe_signature/signature_walk.py`) runs post-merge on the instantiated library — a reconciled signature is gone, a pending one still reported. No change. (Confirmed: `test_bundle_validator.py` 13 passed, pipe_signature suites 43 passed.)
- [x] `PipeLibrary` resolution sees only the winning blueprint. No change. (Confirmed via libraries targeted suite — 100 passed.)

### 🛑 CHECKPOINT A — MANDATORY STOP

Run the **Checkpoint protocol** above. Self-contained milestone: the merge reconciles signature/concrete; two concretes still error. Does **not** yet unblock the goal on its own. Suggested commit message if authorized: `feat(libraries): reconcile PipeSignature with concrete pipe in library merge`.

---

## Phase 2 — Part B: concept references validate at library level

### The problem (verified)

`PipelexBundleBlueprint.validate_local_concept_references` (`pipelex/core/bundles/pipelex_bundle_blueprint.py:145`) runs **per file**, before the merge, and rejects any bare or same-domain-qualified concept ref not declared **in that same file** (native excepted). In a multi-file same-domain library this rejects the additive pattern: a definition file referencing `Summary` (declared in a sibling) fails to parse; declaring `Summary` in both trips the `ConceptLibraryError` duplicate guard. No authoring path through.

Root cause is an **asymmetry**: bare *pipe* refs are already deferred to library-level resolution (`validate_local_pipe_references`, "Bare ref - no validation at bundle level"), which is why cross-file pipe refs work. Concept refs are the only cross-file reference still validated per-file.

### The fix

A per-file validator cannot tell a typo from a valid cross-file ref, so it must stop gating same-domain refs. To preserve the precise error messages it produces today, reproduce the check where all declarations are visible: the merged crate.

### Tasks

- [x] **Relax the per-file validator.** Removed `validate_local_concept_references` (the same-domain "must be declared locally" gate). Syntax/multiplicity validation stays (`PipeBlueprint`/`ConceptBlueprint` field validators). Kept the reference collectors.
- [x] **Promote a public collector.** Renamed `_collect_local_concept_references` → public `collect_concept_references()` (mirrors `collect_pipe_references()`); `_collect_local_refs_from_pipe`/`_concept` stay private. (No redundant wrapper — "promote" = rename to public.)
- [x] **Add library-level reference check** `LibraryCrateFactory._validate_concept_references`, called from `make_from_blueprints` after the merge:
    - skips cross-package (`->`) and external-domain refs; qualifies bare/same-domain to `domain.Code` and requires it in merged `concepts` **or** native;
    - accumulates **all** undeclared refs (ref + context + source) and raises one `ConceptLibraryError` listing each (with "not declared in domain '<domain>'"), plus sorted declared + native concepts;
    - takes `declared_concept_refs: set[str]` (not the concept dict) to sidestep the `TYPE_CHECKING`-only `ConceptBlueprint` param-annotation pitfall;
    - runs **always** (no `allow_signatures` param on `make_from_blueprints`).
- [x] **Duplicate-concept guard unchanged** — untouched; still raises in-loop in `make_from_blueprints` and `_load_concepts_from_blueprints`.
- [x] Verified `ConceptLibraryError` propagation: it is **not** caught by `_translate_to_validate_bundle_error` (whose arms are interpreter/factory/pydantic/run/dry-run/signature). It propagates to the CLI root as a `PipelexError` — **identical** to the already-shipped duplicate-concept `ConceptLibraryError` from the same function. Full CLI-render e2e is folded into Phase 3.
- [x] Grepped the suite: the only other "not declared in domain" expectation is `test_pipelex_bundle_blueprint_pipe_validation.py`, which is for **pipe** refs (`validate_local_pipe_references`, untouched). No relocation needed there.

### Phase 2 tests

- [x] **Relocated** the `test_invalid_*` + `test_error_message_*` cases out of the per-file bundle test into a new library-level module `tests/unit/pipelex/libraries/test_library_crate_concept_references.py` (assert `ConceptLibraryError` from `make_from_blueprints`, same substrings). The per-file file was trimmed to construction smoke tests and renamed `test_pipelex_bundle_blueprint_concept_construction.py` (class `TestPipelexBundleBlueprintConceptConstruction`).
- [x] **Positive cross-file** (order-independent, parametrized): `CROSSREF_CONCEPT_BUNDLE` (declares `Summary`) + `CROSSREF_PIPE_BUNDLE` (refers `Summary` by bare code) → crate builds, ref resolves.
- [x] **Negative cross-file:** `CROSSREF_PIPE_BUNDLE` alone → `ConceptLibraryError` naming `Summary`, context `pipe.make_summary.output`, and source `/fake/crossref_pipe.mthds`.
- [x] Deferred-skip coverage: native, external-domain, and cross-package (structure `concept_ref` `docs->documents.Document`) refs do **not** raise.
- [x] Duplicate-concept collision tests (cross-file + same-file) still green (in `test_library_crate.py`).
- [x] `make agent-check` clean; core + libraries (+ builder + pipeline + pipe_signature + e2e/cli signature) targeted suites green.

### 🛑 CHECKPOINT B — MANDATORY STOP

Run the **Checkpoint protocol**. Part B opens a distinct area (validation layer + a relocated test file) and context will have grown — stop here even though the end-to-end proof is still pending. Record exactly which tests were relocated and the new library-level test module path. Suggested commit message if authorized: `feat(libraries): validate concept references at library level for cross-file refs`.

---

## Phase 3 — End-to-end proof

The real proof that both parts compose: a multi-file `validate bundle <root> -L <dir>` flow, automated as an integration test under `tests/integration/pipelex/`.

### Tasks

- [x] Fixture library (uses the **non-native** shared concept `KeyFinding`): `concepts.mthds` declares `KeyFinding`; `header.mthds` forward-declares `find_key_findings(doc: Text) -> KeyFinding` as `PipeSignature` + a `research_brief` `PipeSequence` controller referencing it by bare code; `definitions.mthds` provides the concrete `find_key_findings` with a matching contract. → `tests/integration/pipelex/libraries/test_additive_multi_file_library.py`.
- [x] Assert: lenient (`--allow-signatures`) passes with the signature present; strict (no flag) passes once the definition is present; concrete wins (`not pipe.is_signature`). Plus cross-batch via `-L` and undeclared→clean `ValidateBundleError`.
- [x] Run **`make agent-test`** (full suite) — green ("All tests passed", exit 0).
- [x] `make agent-check` clean.

### Review findings folded in from the Checkpoint B `/code-review` (xhigh) — fix here

These are end-to-end validate-behavior issues surfaced by the Part B review; they belong in Phase 3, not as a Part B re-open.

- [x] **#1 — `_validate_concept_references` is batch-local (false-positive on valid cross-file refs loaded in separate batches).** ✅ **DONE** — check moved to a pure `validate_concept_references_in_blueprints` called from `load_from_blueprints` (batch ∪ live-library ∪ native). **Plus the discovered second half:** `load_from_crate`'s pipe-factory bare-concept guard (`domain_concept_codes`) was also batch-local — made it library-aware so bare cross-batch refs work end-to-end. `LibraryCrateFactory._validate_concept_references` checks refs only against `set(concepts.keys())` from the blueprints in *that* `make_from_blueprints` call — it has no knowledge of concepts already present in the live `Library` (loaded by a prior, separate `load_from_blueprints`) or in dependency libraries. **CONFIRMED LIVE:** load file A (declares `crossref.Summary`) then file B (bare `Summary` ref) in two separate `load_from_blueprints` calls into the same library → batch 2 wrongly raises `ConceptLibraryError`. Net effect: the cross-file goal is delivered only for the **single-batch / whole-dir** path (`validate_bundles_from_directory`, and `validate bundle <root> -L <dir>` when `root ∈ dir` so it's already loaded in the dir batch). Broken for `root ∉ dir` referencing a `-L` concept, and for any incremental/programmatic load sequence; also `get_crate` (cumulative) and per-batch `load_from_blueprints` disagree on the same library. **Not a regression** (the old per-file validator failed cross-file too), and the docstring's "merged library" oversells it.
    - **DECIDED — move to loader.** Remove `_validate_concept_references` from `make_from_blueprints` (which becomes a pure structural merge + fingerprint) and run it in `load_from_blueprints`, the one place holding **both** the raw blueprints (for `collect_concept_references()` + per-bundle source/context in messages) **and** the live `Library` (for already-loaded concept refs). Validate against `batch concepts ∪ already-loaded library concepts ∪ native`. This also makes `get_crate` and per-batch `load_from_blueprints` agree by construction. `load_from_crate`-only entries (Temporal) skip the check — acceptable: the crate was validated when first built from blueprints. Relocate the factory's `_validate_concept_references` unit tests to the loader level.
    - The Phase 3 integration test **must exercise the cross-batch case** (e.g. concept file loaded via `-L` dir, then a root file referencing it loaded separately) so this is actually proven, not just the single-batch happy path.
- [x] **#2 / #3 — undeclared concept refs surface as a raw, untranslated `ConceptLibraryError` (lost structured reporting + ugly CLI).** ✅ **DONE** — `ConceptLibraryError`/`PipeLibraryError` reparented under `LibraryError`; single `except LibraryError` arm in `_translate_to_validate_bundle_error` (forwards `LibraryLoadingError` structured fields), preceded by `except PipeNotFoundError: raise` so the `--pipe`-slice not-found path keeps its dedicated handler; `_load_mthds_files_into_library` got a surgical `(ConceptLibraryError, PipeLibraryError)` file-context arm. `ConceptLibraryError` from `make_from_blueprints` has no arm in `_translate_to_validate_bundle_error` (`pipelex/pipeline/validate_bundle.py`), and `_validate_pipe_or_bundle` (`pipelex/cli/commands/validate/_validate_core.py`) only catches `FileNotFoundError`/`ValidateBundleError` — so it propagates raw to the typer root. Regression vs the deleted per-file validator, which raised a pydantic `ValidationError` → `PipelexInterpreterError` → structured `ValidateBundleError` (domain/source/concept_code). Also `_load_mthds_files_into_library` only wraps `ValidationError`, so the directory-load path loses its "Could not load blueprints from [files]" file-context wrapper.
    - **DECIDED — reparent then catch once.** Hierarchy finding: `ConceptLibraryError` and `PipeLibraryError` subclass `PipelexError` **directly**, not `LibraryError` (only `LibraryLoadingError` does). Reparent both under `LibraryError`, then add a single `except LibraryError` arm to `_translate_to_validate_bundle_error` and widen the `_load_mthds_files_into_library` catch (currently `ValidationError`-only). One arm then covers undeclared cross-file refs, the **pre-existing** raw duplicate-concept error, and the duplicate-pipe error — all → clean structured `ValidateBundleError`. Class names / `type_uri` / doc slugs are unchanged (low risk). Add a test asserting the CLI/`validate_bundle` surface is clean for an undeclared cross-file ref.

### 🛑 CHECKPOINT C — MANDATORY STOP (UNBLOCK POINT)

Run the **Checkpoint protocol** with the **full** `make agent-test`. This is the unblock point: workers can add definition files in parallel against forward-declared signatures — no in-place overwrites, no transient collisions. Record the green full-suite result and prepare the handoff notes for Phase 4. Suggested commit message if authorized: `test(libraries): end-to-end additive multi-file library (signature + cross-file concept)`.

---

## Phase 4 — Handoff (separate scope — `mthds-plugins` repo + `design.md`)

Different repo (`mthds-plugins`, branch `feature/Recursive-building`). **DONE** — design-doc handoff only; the working tree there is `wip/recursive/design.md` (uncommitted).

- [x] Update `mthds-plugins/wip/recursive/design.md` §2.7 from overwrite-in-place to the **additive** model (forward-declared header + separate definition file). Noted the overwrite model was itself broken by the Part B concept bug (§4.5 "Why the old overwrite-in-place model is retired"). Also flipped the methodology (§2.1/§2.3/§2.5/§2.6), TL;DR, §3 worked example, §4.1/§4.4, §5.2/§5.4 hook nudge, §6 decisions, §7 plan for whole-doc consistency.
- [x] Document the **explicit-`inputs`/`output` on both header and definition** requirement (the exact-match contract) — §2.7 "Contract must match exactly", §2.6 "Contract stability", §4.4 "Contract & collisions", §4.5 "The exact-match contract".
- [x] Adopt the additive flow in the `mthds-vibe` orchestrator and the `mthds-signature-expander` worker — **N/A as a code change: neither exists yet.** The single-pass `mthds-vibe/SKILL.md.j2` is untouched and there is no `agents/`/`mthds-signature-expander`. Instead, `design.md` §4.4/§4.5/§7 (items 3-4) now **prescribe** the additive flow for them, so the downstream §7 implementation builds them additively from the start.

---

## Deferred follow-ups

- **Concepts-only loader skips structure concept-ref validation.** Removing the per-file `validate_local_concept_references` (Part B) means the lightweight concepts-only path (`LibraryManager.load_concepts_only_from_blueprints`, used by `validate_bundle.load_concepts_only*`) no longer rejects an undeclared `concept_ref`/`item_concept_ref` in a concept **structure** field at blueprint construction. **Verified live:** an undeclared structure `concept_ref` loads silently (surfaces only as a debug-logged forward-ref rebuild failure, not a raised error); an undeclared **`refines`** still *does* raise on this path, but via `ConceptFactoryError` during structure-class generation — **not** via `ConceptLibrary.validation_static` (that `@model_validator` does not fire on `add_concepts`, which mutates `root` in place with no `validate_assignment`). The full load path (`load_from_blueprints` → `make_from_blueprints`) — which the recursive/additive flow uses — is fully covered by the new `_validate_concept_references`. Proper fix: validate structure concept refs against the loaded concept set on the concepts-only path too (or fold it into a shared check), so both paths are symmetric. Narrow, secondary path; not blocking the feature.

- **Pre-existing gap (noted, not fixed): partial-hierarchical same-domain typo skipped as external.** In `_validate_concept_references` (and identically in the old per-file validator), a ref like `legal.Foo` when the bundle domain is `legal.contracts` is treated as external (`is_external_to('legal.contracts')` is True because `legal` != `legal.contracts`) and skipped — so the typo escapes the check and only fails later at resolution. Same `QualifiedRef.is_external_to` logic everywhere; not introduced by Part B. Fixing would require a "is `domain_path` a prefix/ancestor of the bundle domain?" notion rather than exact equality — out of scope for this feature.

## Decisions (resolved)

- **Additive over overwrite-in-place.** This plan; `design.md` updated in Phase 4.
- **signature + signature → allow when contracts match** (error on mismatch). Supports a sub-pipe forward-declared by several callers (a DAG).
- **Pipe conformance → exact string match at merge for v1.** Substitutability deferred to the dry-run.
- **Concept references validate at library level, not per file.** Error messages preserved by reproducing the check over the merged crate. Duplicate-concept stays a hard error.
- **Per-file relaxation scope: concepts only.** Pipe per-file validation left as-is (bare pipe refs already deferred; recursive flow uses bare refs). Same-domain *qualified* cross-file refs remain unsupported — the recursive flow does not emit them.
- **Finding #1 (batch-local check) → move to loader (DONE).** `make_from_blueprints` is a pure structural merge + fingerprint; the concept-ref check is the pure `validate_concept_references_in_blueprints` called from `load_from_blueprints`, validating against `batch ∪ already-loaded library concepts ∪ native`. Rejected the "thread known refs into the factory" alternative — the check belongs where library state lives, keeping `make_from_blueprints` world-agnostic. **Implementation discovery:** the check alone is a half-fix — the pipe factory's bare same-domain guard (`load_from_crate`'s `domain_concept_codes`) was also batch-local, so `load_from_crate` now derives it from the live library (relaxing-only; no-op for self-contained crates incl. Temporal). Bare cross-batch refs work end-to-end.
- **Finding #2/#3 (raw error) → reparent under `LibraryError`, catch once (DONE).** `ConceptLibraryError`/`PipeLibraryError` reparented from `PipelexError` to `LibraryError`; a single `except LibraryError` arm in `_translate_to_validate_bundle_error` + a surgical `(ConceptLibraryError, PipeLibraryError)` file-context arm in `_load_mthds_files_into_library` (kept narrow so `LibraryLoadingError`'s structured fields survive). Fixes the new undeclared-ref error and the pre-existing raw duplicate-concept/duplicate-pipe errors uniformly. **Implementation discovery:** `PipeNotFoundError` (a `PipeLibraryError`) has its own CLI handler, so the translate helper gets an `except PipeNotFoundError: raise` ahead of the `LibraryError` arm to keep the `--pipe`-slice not-found path intact.

---

## CHANGELOG (add under `[Unreleased]`; versioned at release time)

```markdown
### Changed

- **Additive multi-file library construction.** Two merge-time rules now support building a same-domain `.mthds` library as separate, additive files (forward-declared headers + separate definitions), enabling parallel top-down method construction:
  - A `PipeSignature` and a concrete pipe with the same code reconcile — the concrete pipe satisfies the signature instead of raising a duplicate-code error. `PipeSignature` works like a forward declaration ("header"), its concrete pipe like the definition; their `inputs`/`output` contracts must match. Two concrete pipes with the same code, or two signatures with differing contracts, remain errors.
  - Concept references resolve against the merged library instead of per file, so a concept declared once can be referenced by bare code from sibling files of the same domain. A concept declared twice remains a `ConceptLibraryError`.
```
