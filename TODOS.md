# Pipe-refs build-time qualification — implementation plan

Source of truth for the design: [wip/pipe-refs/build-time-qualification.md](wip/pipe-refs/build-time-qualification.md) (decided 2026-08-11). Evidence and pre-change state: [wip/pipe-refs/README.md](wip/pipe-refs/README.md). Branch: `fix/Pipe-refs` in the `_refs` worktree — treat this worktree as the repo root.

**What we are doing in one sentence:** bare in-body references (pipe steps, branches, outcomes, batch refs, concept I/O refs) get qualified to their owner domain once, at library build time, via one shared crate pass consumed by both the normalizer and `library_manager`; the live library lookup becomes strict; the crate-wide bare search survives only as an explicitly-named entry-point affordance for user-supplied codes.

## Rules of engagement

- **Checkpoints are mandatory stops.** At each ⛔ CHECKPOINT below, the agent MUST stop working, complete the checkpoint checklist (status updates, gates, commit), and end the session. Do not roll into the next phase in the same session, even if context feels fresh. The next session cold-starts from this file's Status block plus the design doc.
- **Update this file as you go.** Tick checkboxes when items complete; record decisions in the Status block the moment they are taken, not at the end.
- **Gates:** `make agent-check` after code changes; full `make agent-test` before every checkpoint stop (the tree must be left green at every checkpoint). If `make drift-check` opens a contract along the way, resolve it via the drift-review flow — no bypassing.
- **Open questions from the design** are folded into the phase tasks below as explicit decision items (marked OQ1/OQ2/OQ3). Record each ruling in the Status block and in the design doc.

## Status

- **Current phase:** not started (plan written 2026-08-11)
- **Last completed item:** —
- **Decisions taken:** —
- **Surprises / fallout:** —

---

## Phase 1 — the shared pass and the normalizer

The canonical form becomes spec-compliant everywhere the crate is produced. The live library still runs the old rule after this phase — that divergence is known and temporary.

- [ ] Read the design doc and README end-to-end; skim `pipelex/libraries/crate_normalization.py` (`_qualify_concept_ref`, `_qualify_pipe_ref`, `_qualify_io_ref`, `_normalize_pipe`) and `pipelex/libraries/library_crate_factory.py` to confirm the insertion point still matches the design.
- [ ] Extract the in-body reference qualification step out of `crate_normalization.py` into a standalone pass over a `LibraryCrate` (suggested new module: `pipelex/libraries/crate_qualification.py`; final name at implementer's discretion). The pass covers pipe refs (steps, branches, outcomes, batch refs) and concept I/O refs.
- [ ] Switch the pipe rule inside the pass from crate-wide search to **owner-domain qualification** — the exact twin of `_qualify_concept_ref`. Existence is NOT checked by the pass; the ordinary dependency validation catches missing refs afterwards (that is the standard's step 3 by construction).
- [ ] Leave cross-package refs (`alias->…`) untouched by the pass, exactly as the normalizer already does.
- [ ] Make `normalize_crate` consume the shared pass — unchanged in shape, now spec-compliant in rule.
- [ ] Flip the normalizer test that pins the old rule: `tests/unit/pipelex/libraries/test_crate_normalization.py::test_bare_cross_domain_pipe_refs_resolve_to_the_declaring_domain` becomes a test of owner-domain qualification.
- [ ] Re-run the README's demo probes (`wip/pipe-refs/probes/make-demos.sh`) and move the closures accordingly: `fallthrough` and `export-bypass` must now FAIL resolve; `ambiguous` must resolve to the own domain. Update whatever the probes/README record as expected outcomes.
- [ ] `make agent-check` clean.
- [ ] Full `make agent-test` green (the live library is untouched, so the suite must pass as-is).

### ⛔ CHECKPOINT C1 — MANDATORY STOP

A coherent unit has landed: canonical form is spec-compliant everywhere the crate is produced, while the live library still runs the old rule. **This is a known reader divergence — the very next session must start Phase 2; do not park the branch here longer than necessary.**

- [ ] Update the Status block above (phase done, decisions, surprises, corpus fallout).
- [ ] Record status, surprises, and any corpus fallout in the design doc's Phase 1 section (per the design's own instruction).
- [ ] Commit the Phase 1 work on `fix/Pipe-refs` with a clear message.
- [ ] STOP. End the session. Next session starts at Phase 2.

---

## Phase 2 — the live library

The runtime becomes fully spec-compliant and self-consistent. This is the largest phase; the OQ1 investigation comes first because its answer can reshape the dependency-path work.

### Investigation first

- [ ] **OQ1 — dependency-pipe lookup scoping.** Dependency pipes are keyed `alias->domain.code` in the host library, and `pipelex/libraries/library.py` consults per-dependency child libraries during validation. Establish precisely which library a dep pipe's lazy sub-pipe lookup consults at execution time, and confirm the qualified refs produced by the pass resolve correctly in that scope. Record the answer in the design doc (the packaging work needs it regardless).

### The build path

- [ ] Run the qualification pass in `pipelex/libraries/library_manager.py` on **all** crate→pipes paths: main load, secondary loads, dependency-package loads — before pipes are constructed via `PipeFactory.make_from_blueprint`.

### The strict lookup and the entry affordance

- [ ] Strip the step-3 bare-code crate-wide fallback from `PipeLibrary.get_optional_pipe` (`pipelex/libraries/pipe/pipe_library.py`), including the `domain_hint` TODO. What remains: direct key lookup and cross-package (`alias->`) handling. `get_required_pipe`'s signature does not move (transport-pinned).
- [ ] **OQ3 — decide** whether `get_optional_pipe` keeps the cross-package bare-remainder search (`alias->` + bare code). It is alias-scoped so it does not reopen the cross-domain hole; the design leans toward keeping it until the packaging design rules on cross-package reference forms. Record the ruling.
- [ ] Close [wip/parity/d1-domain-hint-deferred.md](wip/parity/d1-domain-hint-deferred.md) as subsumed by this change (status note in that file).
- [ ] **OQ2 — settle the entry affordance's final name and shape** (working name `find_pipe_by_bare_code`; one method or a required/optional pair; where the ambiguity error message lives). Record the ruling.
- [ ] Implement the entry affordance on the pipe library (+ its abstract): exact ref hits directly; a bare code matches crate-wide; ambiguity raises an error asking the user to qualify. Docstring states explicitly that it deliberately does NOT consult `[exports]` — a hand-invoked pipe is not an in-body reference, so package visibility does not apply.
- [ ] Expose it through a new `pipelex/interpreter_hub.py` accessor (additive; the transport spec/conformance update for it happens in Phase 3).
- [ ] Migrate the in-repo entry-shaped call sites to the affordance: the CLI commands (`which`, `show`, `validate`, the `build`/`codegen` groups), `pipeline_run_setup`, and the builder operations. Controllers, `sub_pipe`, `signature_walk`, and `library` validation need NO edit — they look up refs stored on built objects, which now arrive qualified.

### The concept side

- [ ] Collapse `ConceptLibrary.get_required_concept_from_concept_ref_or_code`'s `search_domain_codes` machinery (`pipelex/libraries/concept/concept_library.py` + `concept_provider_abstract.py`) into the same entry-affordance shape: prefer the entry pipe's domain, else crate-wide unique match. Reached only from run-setup input shaping (`stuff_factory` ← `working_memory_factory` / `input_shaper` / `kernel/memory_ops`).
- [ ] In doing so, delete the latent defects README §4 documents: the multi-domain list dying on the first miss, and the miss escaping as the wrong exception class.
- [ ] Decide whether `pipeline_run_setup`'s own-domain-first ordering becomes meaningful or gets deleted along with the list parameter; sweep the callers (`pipeline_run_setup.py`, `runner.py`, `execution_seams.py`, `working_memory_factory.py`, `input_shaper.py`, `stuff_factory.py`, `kernel/memory_ops.py`) for the signature change.

### Footprint cleanups

- [ ] Relax `_pipe_codes_by_file`'s rename collision scope in `pipelex/pipeline/fixes/fix_loop.py` from crate-wide to per-domain (it can only over-block today, but it is part of the rule's footprint).

### Tests

- [ ] Flip the lookup tests that pin the old rule: `tests/unit/pipelex/libraries/test_pipe_library_lookup.py::test_bare_code_ambiguous_raises` and `::test_bare_code_unambiguous` become tests of the strict lookup + entry affordance split.
- [ ] Qualify the refs in tests that construct pipes directly with bare sub-refs (bypassing the crate pass) — they hit the strict lookup now. Find them by running the suite, not by grepping alone.
- [ ] Add conformance-shaped unit coverage for the resolution rows: own-only resolves; sibling-only errors; both-declare resolves to own; nowhere errors. Plus the export-bypass closure case.
- [ ] Add coverage for the entry affordance semantics (exact hit, crate-wide unique bare match, ambiguity error message).

### Gates

- [ ] `make agent-check` clean.
- [ ] Full `make agent-test` green.

### ⛔ CHECKPOINT C2 — MANDATORY STOP

The runtime is fully spec-compliant and self-consistent; only cross-repo work remains.

- [ ] Update the Status block above (decisions on OQ1/OQ2/OQ3, surprises, anything discovered about dependency scoping).
- [ ] Record status in the design doc's Phase 2 section.
- [ ] Re-run the README's probes and demos (`wip/pipe-refs/probes/`) and confirm the post-change behavior matches the design's predictions.
- [ ] Update README §2's table — it describes the pre-change state and becomes historical at this point; mark it as such rather than rewriting history.
- [ ] Update the pipelex `docs/` pages that describe bare-ref resolution, pipe lookup, or the entry surfaces touched here (grep for the old rule's description; docs live in this repo's `docs/`, per workspace convention).
- [ ] Changelog entry under `[Unreleased]` noting the breaking language-behavior change (write "breaking", not "pre-1.0 breaking").
- [ ] Commit the Phase 2 work on `fix/Pipe-refs`.
- [ ] STOP. End the session. Next session starts at Phase 3.

---

## Phase 3 — the coordinated cross-repo set

Land as one coordinated change across sibling repos. Order matters: conformance + transport together, cookbook alongside, `mthds/` last.

### conformance/ + transport surface

- [ ] Add executable conformance cases for the resolution rows (own-only, sibling-only, both-declare, nowhere) and the export-bypass closure — the case nobody would think to write without the visibility argument.
- [ ] Additive transport-surface update: add the new hub accessor to `docs/specs/pipelex-transport-boundary.md` (workspace root) AND `conformance/tests/pipelex_transport/test_data.py` (`ALLOWED_SURFACE`) in the same change, per the spec/conformance sync rule.
- [ ] Run `make check-spec-links` in `conformance/` — must pass.
- [ ] Migrate `pipelex-transport/bridge.py`'s payload-supplied lookup to the new accessor (its code is entry-shaped; `get_required_pipe`'s pinned signature is untouched). This lands together with the spec/`ALLOWED_SURFACE` update above.

### pipelex-cookbook/

- [ ] Qualify the one reference that leans on fall-through: `presentation.present_as_markdown` in `examples/wip/advisory_board/bundle.mthds`.
- [ ] Verify the cookbook example still validates/runs against the updated runtime.

### mthds/ — last

- [ ] Additive clarification at § *Resolution Order for Bare Pipe References*: no-fall-through is what makes `[exports]` enforceable — so the next reader does not mistake the rule for a lookup convenience. No normative change.

### Changelogs

- [ ] Changelog entries in each touched repo noting the breaking language-behavior change, per each repo's convention (skip `wip/` docs in changelogs).

### ⛔ CHECKPOINT C3 — MANDATORY STOP (done)

- [ ] Update the Status block above; all phases complete.
- [ ] Close `wip/pipe-refs/` with a final status note in the design doc and README.
- [ ] Fold the outcome into the parity track's records (`wip/parity/`).
- [ ] Commit; prepare PRs per repo as instructed by the user — do not push or open PRs without being asked.
- [ ] STOP. The work is done; anything further (release sequencing before the packaging system) is a separate track.
