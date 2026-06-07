# TODOS — Make the additive multi-file library model work end-to-end

Two coupled changes unblock **additive, parallel, top-down method building** (designed in `mthds-plugins/wip/recursive/design.md`):

- **Part A — Pipe reconciliation.** A `PipeSignature` and a concrete pipe with the same code reconcile in the library merge (the concrete wins) instead of raising a duplicate-code error.
- **Part B — Concept references validate at library level.** Cross-file, same-domain concept references resolve against the *merged* library instead of being rejected per-file, so a concept declared once can be referenced from sibling files.

Both are required. Part A alone does **not** unblock the goal: any pipe whose contract uses a non-native concept (the common case) cannot be authored additively, because per-file validation rejects a file that references a same-domain concept declared in a sibling file. Verified end-to-end against the design doc's own `research_brief` example — it does not load today.

---

## 📍 Cold-start status — UPDATE AT EVERY CHECKPOINT

> This block is the single source of truth for resuming in a fresh session. A new agent should read this first. Overwrite it at each checkpoint.

- **Branch:** `feature/Support-recursive-design`
- **Plan state:** ✅ finalized, **not started**
- **Current phase:** — (awaiting kickoff of Phase 1)
- **Last verified green:** n/a
- **Next concrete action:** begin Phase 1, Part A — edit `pipelex/libraries/library_crate_factory.py` pipe-merge block
- **Working tree:** only `TODOS.md` modified (this plan). No code changes yet.
- **Decisions/surprises since last checkpoint:** n/a
- **Open questions blocking progress:** none

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

- [ ] **Phase 1 — Part A:** pipe signature/concrete reconciliation → 🛑 **Checkpoint A**
- [ ] **Phase 2 — Part B:** concept references validate at library level → 🛑 **Checkpoint B**
- [ ] **Phase 3 — End-to-end proof** + full suite + lint → 🛑 **Checkpoint C (UNBLOCK POINT)**
- [ ] **Phase 4 — Handoff** (separate scope, `mthds-plugins` repo + `design.md`)

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

- [ ] Replace the duplicate-detection branch in the pipe loop with a `_reconcile_pipe_collision(...)` call (snippet below).
- [ ] Add `_reconcile_pipe_collision` (classmethod), `_contracts_match` (staticmethod), `_duplicate_pipe_msg` (the current same-file vs cross-file messages), and `_contract_mismatch_msg`.
- [ ] `_contract_mismatch_msg` must read correctly for **both** signature+concrete and signature+signature (two headers can disagree). Phrase as "declared with mismatched contracts," not "a signature and its implementation."
- [ ] Add unit tests + fixtures (see below).
- [ ] `make agent-check` clean; libraries targeted suite green.

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

- [ ] signature **then** concrete (cross-file) → concrete wins; `crate.pipes[ref].is_signature is False`; `source_map[ref]` is the concrete's file.
- [ ] concrete **then** signature (reverse order) → concrete wins; same assertions (order-independence).
- [ ] signature + signature, matching contract → one survives, still a signature.
- [ ] signature + signature, mismatched contract → `PipeLibraryError`.
- [ ] signature + concrete, mismatched inputs/output → `PipeLibraryError`.
- [ ] signature with explicit `inputs` + concrete that **omits** `inputs` → `PipeLibraryError` (pins exact-match; documents the orchestrator requirement).
- [ ] New fixtures: a `PipeSignatureBlueprint` for an existing concrete code (matching contract), a mismatched-contract concrete, a second signature variant. Mirror the `SCORING_*` shape.

### Downstream — confirm only, no change expected

- [ ] Signature pre-pass (`pipelex/pipeline/bundle_validator.py::_signature_pre_pass`, `pipelex/pipe_signature/signature_walk.py`) runs post-merge on the instantiated library — a reconciled signature is gone, a pending one still reported. No change.
- [ ] `PipeLibrary` resolution sees only the winning blueprint. No change.

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

- [ ] **Relax the per-file validator.** Remove the same-domain "must be declared locally" gate. Syntax/multiplicity validation stays (in `PipeBlueprint.generic_validate_inputs/output` and `ConceptBlueprint`). External-domain + cross-package refs remain deferred. With the local gate gone the validator does nothing useful → remove `validate_local_concept_references`; **keep** the reference collectors (`_collect_local_concept_references`, `_collect_local_refs_from_pipe`, `_collect_local_refs_from_concept`).
- [ ] **Promote a public collector.** Add `collect_concept_references()` on `PipelexBundleBlueprint` (mirroring the existing public `collect_pipe_references()`) returning `(concept_ref_or_code, context)` pairs, for the factory to consume.
- [ ] **Add library-level reference check** in `LibraryCrateFactory.make_from_blueprints`, after the merge (full `concepts` dict known). For each blueprint's collected refs (factory has each ref's `domain` + `source`):
    - skip cross-package (`->`); skip external-domain (qualified to a different domain);
    - otherwise qualify bare/same-domain to `domain.Code` and require it in merged `concepts` **or** native;
    - accumulate undeclared refs with context + source; raise `ConceptLibraryError` listing **all** of them with the same message content as today (offending ref, context path, source file, sorted declared concepts, sorted native concepts).
    - Runs **always** (not gated by `--allow-signatures`): a signature mocks a pipe's output *value*, not the concept's existence.
- [ ] **Duplicate-concept guard unchanged** — two declarations of the same concept code stay a `ConceptLibraryError`.
- [ ] Verify the `ConceptLibraryError` from `make_from_blueprints` surfaces cleanly through `validate bundle` (load path: `library_manager.load_from_blueprints` → `make_from_blueprints`). It is a `PipelexError` subclass, so it should propagate like the others; confirm the CLI message is clean.
- [ ] Grep the suite for other tests that construct a single-file bundle expecting a per-file "not declared in domain" `ValidationError` (beyond the dedicated file) and relocate/adjust them.

### Phase 2 tests

- [ ] **Relocate** `test_invalid_*` cases from `tests/unit/pipelex/core/bundles/test_pipelex_bundle_blueprint_concept_validation.py` to a library-level test (assert `ConceptLibraryError` from `make_from_blueprints`, same message substrings). `test_valid_*` per-file-construction cases can stay (construction still succeeds), but reference-resolution coverage now lives at library level.
- [ ] **Positive cross-file:** concept declared in file A, referenced by bare code from a pipe in file B (same domain) → crate builds, ref resolves.
- [ ] **Negative cross-file:** concept referenced (bare) but declared in no file → `ConceptLibraryError` naming the ref + source.
- [ ] Keep duplicate-concept collision tests (cross-file + same-file) green.
- [ ] `make agent-check` clean; core + libraries targeted suites green.

### 🛑 CHECKPOINT B — MANDATORY STOP

Run the **Checkpoint protocol**. Part B opens a distinct area (validation layer + a relocated test file) and context will have grown — stop here even though the end-to-end proof is still pending. Record exactly which tests were relocated and the new library-level test module path. Suggested commit message if authorized: `feat(libraries): validate concept references at library level for cross-file refs`.

---

## Phase 3 — End-to-end proof

The real proof that both parts compose: a multi-file `validate bundle <root> -L <dir>` flow, automated as an integration test under `tests/integration/pipelex/`.

### Tasks

- [ ] Fixture library (must use a **non-native** shared concept — a native-only contract would pass even with the bug present and give false confidence):
    - file declaring a non-native intermediate concept (e.g. `KeyFinding`);
    - a header file forward-declaring `find_key_findings(... ) -> KeyFinding` as `PipeSignature`, plus a controller referencing it by bare code;
    - a sibling **definition** file providing concrete `find_key_findings` with a matching contract.
- [ ] Assert: lenient validation (`--allow-signatures`) passes with the signature present (this is the case that fails today); strict validation (no flag) passes once the definition is present; the concrete wins.
- [ ] Run **`make agent-test`** (full suite — change spans `libraries/` + `core/` + load path). Must be green.
- [ ] `make agent-check` clean.

### 🛑 CHECKPOINT C — MANDATORY STOP (UNBLOCK POINT)

Run the **Checkpoint protocol** with the **full** `make agent-test`. This is the unblock point: workers can add definition files in parallel against forward-declared signatures — no in-place overwrites, no transient collisions. Record the green full-suite result and prepare the handoff notes for Phase 4. Suggested commit message if authorized: `test(libraries): end-to-end additive multi-file library (signature + cross-file concept)`.

---

## Phase 4 — Handoff (separate scope — `mthds-plugins` repo + `design.md`)

Different repo / likely a fresh session. Do not start before Checkpoint C is green.

- [ ] Update `mthds-plugins/wip/recursive/design.md` §2.7 from overwrite-in-place to the **additive** model (forward-declared header + separate definition file). Note the overwrite model was itself broken by the Part B concept bug.
- [ ] Document the **explicit-`inputs`/`output` on both header and definition** requirement (the exact-match contract).
- [ ] Adopt the additive flow in the `mthds-vibe` orchestrator and the `mthds-signature-expander` worker.

---

## Decisions (resolved)

- **Additive over overwrite-in-place.** This plan; `design.md` updated in Phase 4.
- **signature + signature → allow when contracts match** (error on mismatch). Supports a sub-pipe forward-declared by several callers (a DAG).
- **Pipe conformance → exact string match at merge for v1.** Substitutability deferred to the dry-run.
- **Concept references validate at library level, not per file.** Error messages preserved by reproducing the check over the merged crate. Duplicate-concept stays a hard error.
- **Per-file relaxation scope: concepts only.** Pipe per-file validation left as-is (bare pipe refs already deferred; recursive flow uses bare refs). Same-domain *qualified* cross-file refs remain unsupported — the recursive flow does not emit them.

---

## CHANGELOG (add under `[Unreleased]`; versioned at release time)

```markdown
### Changed

- **Additive multi-file library construction.** Two merge-time rules now support building a same-domain `.mthds` library as separate, additive files (forward-declared headers + separate definitions), enabling parallel top-down method construction:
  - A `PipeSignature` and a concrete pipe with the same code reconcile — the concrete pipe satisfies the signature instead of raising a duplicate-code error. `PipeSignature` works like a forward declaration ("header"), its concrete pipe like the definition; their `inputs`/`output` contracts must match. Two concrete pipes with the same code, or two signatures with differing contracts, remain errors.
  - Concept references resolve against the merged library instead of per file, so a concept declared once can be referenced by bare code from sibling files of the same domain. A concept declared twice remains a `ConceptLibraryError`.
```
