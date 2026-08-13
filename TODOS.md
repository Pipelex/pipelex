# Pipe-refs build-time qualification — implementation plan

Source of truth for the design: [wip/pipe-refs/build-time-qualification.md](wip/pipe-refs/build-time-qualification.md) (decided 2026-08-11). Evidence and pre-change state: [wip/pipe-refs/README.md](wip/pipe-refs/README.md). Venue: the `_refs` worktree — treat this worktree as the repo root.

**What we are doing in one sentence:** bare in-body references (pipe steps, branches, outcomes, batch refs, concept I/O refs) get qualified to their owner domain once, at library build time, via one shared crate pass consumed by both the normalizer and `library_manager`; the live library lookup becomes strict; the crate-wide bare search survives only as an explicitly-named entry-point affordance for user-supplied codes.

**Why it matters beyond tidiness:** no-fall-through is what makes `[exports]` enforceable. A visibility rule the resolver can reach around is not a visibility rule. Keep that argument at the front of every discussion about this change — it is the reason the blast radius is worth paying.

## The resolution rule, in one picture

```
in-body ref encountered
        |
        +-- contains "alias->" ? --YES--> cross-package: pass leaves it ALONE
        |                                 (resolved against the child library)
        NO
        |
        +-- already qualified "d.c" ? --YES--> unchanged (pass is idempotent)
        |
        NO  (bare code "c")
        |
        v
   qualify to the OWNER domain of the declaring pipe  -->  "own_domain.c"
        |
        |  existence is NOT checked here
        v
   ordinary dependency validation
        |
        +-- resolves ? --YES--> done
        |
        NO
        v
   error names the ref that was tried, and suggests a crate-wide
   candidate when one exists (diagnostic scan, FAILURE PATH ONLY —
   this is not a resolution fallback)
```

Entry-shaped lookups (a human typing a pipe code at a CLI) do NOT follow that rule. They go through the entry affordance, which searches crate-wide, refuses ambiguity, and deliberately ignores `[exports]` — a hand-invoked pipe is not an in-body reference, so package visibility does not apply.

## Rules of engagement

- **Checkpoints are mandatory stops.** At each ⛔ CHECKPOINT below, the agent MUST stop working, complete the checkpoint checklist (status updates, gates, commit), and end the session. Do not roll into the next phase in the same session, even if context feels fresh. The next session cold-starts from this file's Status block plus the design doc.
- **Update this file as you go.** Tick checkboxes when items complete; record decisions in the Status block the moment they are taken, not at the end.
- **Open questions from the design** are folded into the phase tasks below as explicit decision items (marked OQ1/OQ2/OQ3). Record each ruling in the Status block and in the design doc. OQ1 is a go/no-go gate in Phase 0, not an implementation task.

### Gates — the full checklist, run at every checkpoint

`make agent-check` and `make agent-test` do not cover everything this plan disturbs. Three of the gaps fail silently, which is why this is a checklist and not a sentence.

1. `make agent-check` clean.
2. Full `make agent-test` green.
3. **`git add` the work, THEN `make drift-check`.** `agent-check` does not run `drift-check`, so a contract never opens "along the way" under the other gates. And `drift-check` reads the git *index*, so unstaged work reads as a false green. If a contract opens, resolve it via the drift-review flow — no bypassing.
4. **Reconcile `.test_durations`** after any test file, class, or function is renamed or repurposed. This plan repurposes named tests in both the normalizer and lookup suites. Orphan node ids are silent — pytest-split treats an unknown id as average duration. Collect with `.venv/bin/pytest --collect-only -q -m ""`; the marker filter in `addopts` hides a large slice of the suite (mostly `tests/e2e`) and makes every e2e entry look like an orphan.
5. **Record the subject grant BEFORE the first `agent-check` on the new module.** `agent-check` runs `fix-keyword-only`, which silently rewrites an ungranted positional subject to keyword-only. If the pass is meant to read as a verb–object sentence (`qualify_crate(crate)`), `make subject-grant` has to land first or the shape is gone before anyone decides.

## Status

- **Current phase:** Phase 2 COMPLETE (checkpoint C2 passed 2026-08-11). Next session starts at Phase 3.
- **Last completed item:** C2 — the rule flipped to owner-domain qualification, the live `PipeLibrary` lookup made strict, the entry affordance built and every entry-shaped call site migrated. The export bypass is **measurably closed**: the `export-bypass` demo closure that used to reach a non-exported pipe by bare code now fails to resolve, and `ambiguous` now resolves to the own domain (re-measured table in `wip/pipe-refs/README.md` §3).
- **Decisions taken:** phase structure reworked so no checkpoint rests on a self-contradicting tree; OQ1 promoted to a Phase 0 go/no-go gate; breaking-change posture held (no deprecation period) but preceded by a bounded corpus measurement. **OQ1 ruled GO** — owner-domain qualification is neutral-to-better for dependency packages; the dependency lookup-scope defect it exposed is pre-existing and deferred to the packaging project (`wip/pipe-refs/dependency-subpipe-scope-deferred.md`). **Crate envelope ruled: the pass does not deal in crates at all** — it returns a `QualifiedCrateContent` (just `concepts` and `pipes`), never a `LibraryCrate`, because it cannot pick the right digest scheme for a `fingerprint`. Each consumer makes the fingerprint correct at its own boundary (rationale in the design doc's Phase 1 outcome). *(This bullet previously read "the pass is envelope-preserving", describing the first cut that returned a crate; review changed the return type and the wording was stale in three places until a PR bot caught one of them.)*
- **Surprises / fallout:** (1) the dependency execution path has **no** child-library scoping at all — a dependency package using a controller internally either fails to load or silently binds a host pipe of the same bare code; the child-library special case in `Library.validate_pipe_library_with_libraries`'s first loop is neutralized by `pipe.validate_with_libraries()` in the second. Worse in the shape a package actually ships: with a manifest `[exports]`, the authored helper is dropped from the dependency's own child library and the load fails earlier still. (2) README §5's corpus scan used a hardcoded repo list that reached under a fifth of the bundles outside this repo; the widened scan is in `wip/pipe-refs/corpus-measurement.md`, and the second breaking reference lives in `cocode` — a shipped CLI, not an examples directory.
- **Open risks carried in:** four latent defects surfaced by the outside-voice pass are folded into Phases 1–3 below (batched sub-pipe code derivation, transported `PipeFunc` bare codes, the crate fingerprint contract — now ruled, aliased dependency keys polluting the crate-wide search). None of them is speculative; each names a file.
- **Phase 1 findings that change how Phase 2 must be tested:** (1) **this repo's entire bundle corpus is blind to the rule flip** — applying Phase 2's owner-domain rule to all 54 crates buildable here produces byte-identical output, so the two-domain fixture is not a nicety and the mutation check is what makes the resolution-row tests mean anything; (2) **a differential harness whose inputs each carry at most one defect cannot see an error-precedence change** — that is how Phase 1's own precedence shift got past it and had to be caught in review; Phase 2 moves far more error surface, so its equivalence inputs need multi-defect crates; (3) **a fixture full of bare refs proves nothing unless a test reads a ref back out of the result** — Phase 1's first test module passed intact against a no-op pass for exactly that reason; (4) nothing writes a normalized crate back over a `.mthds` file, so the flip does not rewrite user source — but the stamped `codegen.lock` `crate_fingerprint` moves on every committed projection; (5) `_qualify_io_ref`'s cross-package guard looks unreachable through a constructed blueprint (the io-ref validator rejects `alias->` refs outright) — preserved verbatim, flagged for whichever phase owns cross-package forms.
- **Phase 2 rulings.** **OQ2 — the entry affordance is a `get_optional_entry_pipe` / `get_required_entry_pipe` pair** on `PipeLibraryAbstract` + `PipeLibrary`, mirrored as hub accessors. A pair rather than one method because the migration found exactly one caller (`pipelex which`) that needs the optional form and eleven that want the required one; "entry" rather than the working name `find_pipe_by_bare_code` because it also takes fully-qualified refs, and because the name should say *why* the lookup differs, not *how*. **OQ3 — the cross-package bare-remainder search stays.** The qualification pass leaves `alias->…` refs alone (it cannot know a dependency's domain layout), so deleting the search would break every `alias->bare_code` ref with no canonical spelling to migrate to. It is alias-scoped and cannot reach a host pipe; the comment in `get_optional_pipe` says so and points at the packaging design. **DRY — the pipe and concept affordances stay separate**, written up with the reasoning in [wip/pipe-refs/entry-affordance-share-vs-duplicate.md](wip/pipe-refs/entry-affordance-share-vs-duplicate.md) so Phase 3 inherits a decision rather than making an accidental copy. The *rule* is shared (one `qualify_crate`); the affordance is the deliberate exception to it, and the two should not be conflated.
- **Phase 2 surprises.** (1) **The batched sub-pipe defect was real but not what the review said.** The plan (from Codex) predicted the invalid code `domain.foo_batch`; in fact `PipeAbstract` has a `code` validator that strips a namespace prefix, so the built ref was correct all along. What the wrong derivation actually produced was a `log.warning` on **every** batched run, about a code no user wrote. The fix stands; the first test written for it asserted on the ref and passed against the bug, and had to be rewritten to assert on the warning. (2) **Two call sites the plan did not enumerate** turned up by running the suite rather than grepping: `validate_bundle.py` resolved a bundle's own `[pipe.<code>]` keys as bare codes (now qualified with the bundle's domain — precise, not routed through the affordance), and `dry_run_in_process.best_effort_graph_spec` resolved a caller-supplied graph target (entry-shaped, now on the affordance). The second silently degrades to "no graph" on a miss, so it would never have failed loudly. (3) **`missing_pipe_code` changed value** — a structured, machine-read field, so a wire-visible change, recorded in the changelog. (4) The test sweep's own derivation over-reached twice and both were caught by verification rather than by the suite: a `.pipe_code ==` assertion resolved against the wrong source (that field is the *referring* pipe's local code and does not change), and a ref inside a `PipelexBundleBlueprint` fixture was hand-qualified when the product qualifies it — the new break message diagnosed that one itself.
- **Phase 2 PR review (cubic, 9 findings; greptile clean).** Two were real defects and both are fixed: the `SpecialOutcome` exemption applied to *every* controller kind, though `continue` / `fail` are legal snake_case pipe codes — so a sequence step naming a pipe called `continue` was left unqualified, which the strict lookup then fails to resolve (a Phase 2 regression: the fall-through used to rescue it); and `make-demos.sh`'s `mktemp -d -t` is BSD-only, so the README's own reproduction command aborted on Linux before writing a demo. **Four findings were claims of mine that had gone false**, which is the half worth remembering: the `python_sources` deferral credited `model_copy` for envelope preservation (true of the pass's *first* cut, which returned a crate — the same stale claim was in three places, and the bot found one), "no fix op writes a pipe ref" is wrong (`strip-namespace` plans a root `main_pipe` SET_KEY), and three line-number pointers had gone stale *inside this branch* between Phase 1 and Phase 2. Those were fixed by **removing** the line numbers, not correcting them — a pointer into code the same branch edits re-stales itself every phase.
- **The `_domain_of` / `CrateNormalizationError` debt, split and settled.** Phase 1 left two things wrong-sounding once `library_manager` became a second caller of the pass, and parked both on Phase 2. **Only one of them was Phase 2's to pay**, which the plan did not say clearly enough — a PR bot caught the bullet still assigning both to a phase declared complete. Settled: the **message** is fixed here (it now says "this pass expects…" rather than blaming the normalizer, which is no longer even the busier caller). The **error-class rename is deliberately re-deferred to Phase 4b**, where it belongs: `error_type` is a wire string, so a rename needs `make generate-error-identity`, `make generate-error-pages`, and the TypeScript-consumer sweep — all of which are already Phase 4b's "error-surface sweep" line items. Doing it here would open a cross-repo surface inside a runtime-only phase.

---

## Phase 0 — answer the questions that can invalidate the design

Nothing here writes product code. Both items exist because their answers can change what gets built, and both are cheaper now than later.

- [x] **OQ1 — dependency-pipe lookup scoping (GO/NO-GO).** **Answered: GO.** Measured with `wip/pipe-refs/probes/dep-subpipe-scope.py` across three package shapes. Execution consults the **host** library unconditionally, and its bare-code fall-through skips `alias->` entries — so a dependency's own bare sub-pipe ref never reaches the dependency's own pipe *today*: a plain host fails to load, a host declaring the same bare code loads and silently binds the host's pipe, and a dependency with a real `[exports]` manifest fails earlier still because the export filter drops the authored helper from the child library. Owner-domain qualification does not regress that (the qualified ref resolves to `None` in the host exactly as the bare one does), converts the silent capture into a deterministic not-found, and makes the eventual package-scoped lookup a direct key hit in the child library. The pre-existing defect is written up in `wip/pipe-refs/dependency-subpipe-scope-deferred.md` and deferred to the packaging project.
- [x] **Measure the fall-through corpus.** **Two bare pipe refs break across every `.mthds` tree in the workspace**, each fixed by one qualified spelling. Recorded with the full table, the reproduction command and the denominator's caveats in `wip/pipe-refs/corpus-measurement.md`. README §5's scan used a hardcoded ten-repo list and missed most of the workspace; enumerating instead multiplies the corpus several times over and finds a second `sibling-only` case in `cocode` — a shipped CLI, not a sample. The `sibling-only` *concept* refs found are vscode-pipelex editor fixtures that already fail to load today, so they are not new breakage.

### ⛔ CHECKPOINT C0 — MANDATORY STOP

- [x] Record the OQ1 ruling and the corpus number in the Status block and the design doc.
- [x] If OQ1 came back negative, do not proceed — write up what broke the premise and end the session for a design conversation. *(Came back positive — proceeding.)*
- [x] Commit the investigation notes.
- [x] STOP. Next session starts at Phase 1.

---

## Phase 1 — extract the pass (pure refactor, behavior-identical)

This phase moves code and changes nothing. That is the point: the checkpoint at the end is the safest handoff state in the whole plan, provable by an unchanged test suite. The rule flip does not happen here.

- [x] Read the design doc and README end-to-end; skim `pipelex/libraries/crate_normalization.py` (`_qualify_concept_ref`, `_qualify_pipe_ref`, `_qualify_io_ref`, `_normalize_pipe`) and `pipelex/libraries/library_crate_factory.py` to confirm the insertion point still matches the design.
- [x] **Record the subject grant first if the pass takes a positional subject** (see Gates item 5). Done — nine grants recorded before the first check. The `PostToolUse` hook blocked the write and named every ungranted subject, so the auto-fixer never got the chance to rewrite them; the gate's hazard is real but the hook catches it at edit time, not only at `agent-check` time.
- [x] Extract the in-body reference qualification step out of `crate_normalization.py` into a standalone pass over a `LibraryCrate`. Landed as `pipelex/libraries/crate_qualification.py::qualify_crate`. Covers pipe refs (steps, branches, outcomes, batch refs), concept I/O refs, `refines`, and structure-field refs. **Rule unchanged** — crate-wide search stays.
- [x] Make `normalize_crate` consume the extracted pass. No test flips. **Behavior-identical with one known, deliberate exception — error precedence between two independent defects.** HEAD's implementation was loaded beside the working tree's and both run over the same inputs, comparing full serialized output: identical across every crate buildable from this repo's `.mthds` files and across ten hand-built crates covering the branches the corpus cannot reach. The comparison was mutation-checked so its green means something: dropping structure-field qualification reddens one case, applying the Phase 2 rule reddens three.

    ⚠ **The exception, and how it was missed.** Qualification now runs as one complete phase ahead of refinement flattening, where HEAD interleaved them (concepts → flatten → pipes). A crate carrying *both* a refinement cycle and an ambiguous bare pipe ref used to report the cycle and now reports the ref. **The differential harness could not see this: every crate it compares carries at most one defect.** A single-defect corpus cannot detect a precedence change by construction — the finding came from review, not from the harness, and that is the lesson worth carrying into Phase 2, where far more error paths move. Accepted rather than fixed: restoring the old order would mean splitting the pass in two so the normalizer could interleave it, and Phase 2 runs the pass with no flattening at all. Both errors are `CrateNormalizationError`, the crate is invalid either way, and which of two independent defects is named first is not a contract. Recorded in `normalize_crate`'s docstring.
- [x] **Inventory every consumer of normalized crate output before the flip phase.** Recorded in [wip/pipe-refs/normalized-crate-consumers.md](wip/pipe-refs/normalized-crate-consumers.md). **The feared write-back does not exist** — no path writes a normalized crate back over a `.mthds` source file. `pipelex fix` rewrites user files but never through a crate, and no fix op writes a pipe ref (re-check in Phase 2 rather than assume). What does move is the stamped `codegen.lock` `crate_fingerprint` on every committed projection.
- [x] **Settle the crate envelope / fingerprint contract.** **Ruled: the pass does not deal in fingerprints at all** — it returns a `QualifiedCrateContent` (the rewritten `concepts` and `pipes`), not a `LibraryCrate`. Returning a crate would force it to supply a `fingerprint` it cannot get right, since a crate does not record which digest scheme produced its value; the pass would have to guess or carry over a digest that no longer describes its own content, contradicting `LibraryCrate.fingerprint`'s own docstring. Returning the two mappings makes that unrepresentable and costs the callers nothing — both already hold a crate to read the envelope from, and `normalize_crate` builds a fresh one anyway. Phase 2's `load_from_crate` keys idempotency on the incoming crate's fingerprint, which is what external callers pass to `is_crate_loaded`. *(First cut returned a crate with the envelope carried over and a paragraph excusing the stale digest; review pushed back and the smaller surface is plainly better — a paragraph of excuse is a design smell.)* The related `python_sources` drop in `normalize_crate` is real, untouched here, and deferred in [wip/pipe-refs/normalize-crate-drops-python-sources-deferred.md](wip/pipe-refs/normalize-crate-drops-python-sources-deferred.md) — the one-line fix moves customer Python source into a CLI stdout stream and an HTTP response body.
- [x] Gates checklist clean (all five items).

### ⛔ CHECKPOINT C1 — MANDATORY STOP

A pure refactor has landed. The tree is fully self-consistent and the suite is unchanged — this is a genuinely safe place to walk away from.

- [x] Update the Status block (phase done, the consumer inventory, the fingerprint ruling).
- [x] Record status in the design doc's Phase 1 section.
- [x] Commit with a clear message. ⚠ **This item's own wording had to change:** it said "say plainly that this commit changes no behavior", and that turned out not to be true. The message states the extraction is behavior-preserving *with one documented exception* and names it. An instruction to assert a property is not a licence to assert it unverified.
- [x] Gates run at the checkpoint: `agent-check` clean, full `agent-test` green, `drift-check` passed against the staged index, `.test_durations` N/A (path-existence gate; nothing renamed or moved), subject grants recorded ahead of the first check.
- [x] Reviewed by a no-context `/code-review` fan-out; findings triaged and verified individually rather than deferred to. Three of the reviewer's claims held up, two against claims I had written down myself.

---

## Phase 2 — flip the rule and make the lookup strict (these land together)

The normalizer and the live library must never disagree in a committed state, so the rule flip and the strict lookup are one phase. This is the phase that justifies the branch.

### The rule

- [x] Switch the pipe rule inside the pass from crate-wide search to **owner-domain qualification** — the exact twin of `_qualify_concept_ref`. Existence is NOT checked by the pass; the ordinary dependency validation catches missing refs afterwards (that is the standard's step 3 by construction).
- [x] Leave cross-package refs (`alias->…`) untouched by the pass, exactly as the normalizer already does.
- [x] **Fix the batched sub-pipe code derivation.** `SubPipe.pipe_code` becomes `domain.foo`, and the runtime derives `f"{self.pipe_code}_batch"` (`pipe_batch_adhoc_pipe_code` in `pipelex/pipe_controllers/sub_pipe.py`). Use the resolved sub-pipe's local code for that derivation. ⚠ **The predicted consequence turned out to be wrong** — see the Phase 2 surprises above: `PipeAbstract`'s `code` validator strips a namespace prefix, so the built ref was correct all along and what the bug really produced was a warning on every batched run.
- [x] Run the qualification pass in `pipelex/libraries/library_manager.py` on **all** crate→pipes paths — main load, secondary loads, dependency-package loads — before pipes are constructed via `PipeFactory.make_from_blueprint`.

### The strict lookup and the entry affordance

- [x] Strip the step-3 bare-code crate-wide fallback from `PipeLibrary.get_optional_pipe` (`pipelex/libraries/pipe/pipe_library.py`), including the `domain_hint` TODO. What remains: direct key lookup and cross-package (`alias->`) handling. `get_required_pipe`'s signature does not move (transport-pinned).
- [x] **OQ3 — decide** whether `get_optional_pipe` keeps the cross-package bare-remainder search (`alias->` + bare code). It is alias-scoped so it does not reopen the cross-domain hole; the design leans toward keeping it until the packaging design rules on cross-package reference forms. Record the ruling, and pin it with a test either way.
- [x] Close [wip/parity/d1-domain-hint-deferred.md](wip/parity/d1-domain-hint-deferred.md) as subsumed by this change (status note in that file).
- [x] **OQ2 — settle the entry affordance's final name and shape** (working name `find_pipe_by_bare_code`; one method or a required/optional pair; where the ambiguity error message lives).
- [x] Implement the entry affordance on the pipe library (+ its abstract): exact ref hits directly; a bare code matches crate-wide; ambiguity raises an error asking the user to qualify. Docstring states explicitly that it deliberately does NOT consult `[exports]` — a hand-invoked pipe is not an in-body reference, so package visibility does not apply.
- [x] **Exclude aliased dependency keys from the crate-wide bare search.** `PipeLibrary.root` also holds `alias->…` dependency entries (added by `add_dependency_pipe`), so "crate-wide" is not "every value in root". Without this exclusion, installing an unrelated dependency package can make a host pipe ambiguous — reintroducing, through the new affordance, exactly the contextual instability this branch exists to eliminate. Applies to the concept affordance in Phase 3 too.
- [x] **Decide and record the share-vs-duplicate question** between this pipe affordance and the concept affordance built in Phase 3. They are near-twins — the concept one adds a domain-preference step, and its spec currently stops at "unique match" without saying what happens when the match is not unique. Decide now whether they share a helper or stay deliberately separate, and settle whether the concept one raises on ambiguity. A written "separate, because X" is a valid answer; an accidental copy discovered in Phase 3 is not.
- [x] Expose the affordance through a new `pipelex/interpreter_hub.py` accessor (additive; the transport spec/conformance update for it happens in Phase 4b).
- [x] Migrate the in-repo entry-shaped call sites to the affordance: the CLI commands (`which`, `show`, `validate`, the `build`/`codegen` groups), `pipeline_run_setup`, and the builder operations. Controllers, `sub_pipe`, `signature_walk`, and `library` validation need NO edit — they look up refs stored on built objects, which now arrive qualified. ⚠ That is true *only because this phase lands as one change*: `Library.validate_pipe_library_with_libraries`'s first loop looks up a bare sub-pipe code against the child library, whose keys are qualified, so it is served today solely by the step-3 fall-through being deleted below. Deleting the fall-through without qualifying the dependency load path breaks it.
- [x] **Qualify the transported `PipeFunc` code.** `PipeFunc` used to send its bare code and the sandbox later calls the now-strict lookup with it (`pipelex/pipe_operators/func/pipe_func.py` → `pipelex/pipe_operators/func/direct_pipe_func_executor.py`). Under the strict lookup **every** transported `PipeFunc` fails, not merely ambiguous ones. The DTO must carry a qualified ref — it now transports `pipe_code=self.pipe_ref`.

### The break message

- [x] Spec the not-found message in **dependency validation** — that is where users actually meet it, not in the lookup. It names the qualified ref that was tried, and when a crate-wide candidate exists it suggests it and states the new rule. Without this, the user reads `advisory.present_as_markdown` while staring at a file that says `present_as_markdown`, and has no way to know the compiler added the prefix.
- [x] Mark the diagnostic crate-wide scan **failure-path only** in code and comment. It is the same scan being deleted from the resolution path, and an implementer in a hurry can reintroduce the fallback by accident.
- [x] Build the crate-wide bare-code index **once per validation run** and share it across every missing-ref diagnostic. Per-error scanning goes quadratic on the mass-breakage run — which is precisely the first-run-after-upgrade this feature exists to improve.

### Tests

- [x] **Build a two-domain fixture.** In a single-domain crate, owner-domain qualification and crate-wide search give identical answers, so every resolution-row test below would pass just as happily under the rule being deleted. The rows only discriminate when a sibling domain declares the same pipe code. ⚠ **Measured in Phase 1, not merely suspected:** applying this phase's rule to all 54 crates buildable from this repo's `.mthds` files changes nothing — every normalized output is byte-identical under both rules. The repo's own corpus is blind to the flip, so the fixture must be hand-built, and the mutation check below is what proves it discriminates.
- [x] Flip the normalizer test that pins the old rule: `tests/unit/pipelex/libraries/test_crate_normalization.py::test_bare_cross_domain_pipe_refs_resolve_to_the_declaring_domain` becomes a test of owner-domain qualification.
- [x] Flip the lookup tests that pin the old rule: `tests/unit/pipelex/libraries/test_pipe_library_lookup.py::test_bare_code_ambiguous_raises` and `::test_bare_code_unambiguous` become tests of the strict lookup + entry affordance split.
- [x] Qualify the refs in tests that construct pipes directly with bare sub-refs (bypassing the crate pass) — they hit the strict lookup now. Find them by running the suite, not by grepping alone.
- [x] Conformance-shaped unit coverage for the resolution rows on the two-domain fixture: own-only resolves; sibling-only errors; both-declare resolves to own; nowhere errors. ⚠ **The export-bypass closure case is NOT covered by a test here** — only by re-running the demo probe by hand (recorded in README §3). Its *behaviour* is covered: a bare in-body ref cannot reach **any** sibling domain, exported or not, which is pinned at library level by `test_unresolved_pipe_ref_message.py::test_names_the_qualified_ref_and_explains_the_rule`, and export-bypass is a strict subcase of that. What has no test is the `[exports]`/`METHODS.toml` machinery *interacting* with the new rule, which needs a package fixture and is conformance-shaped — it is already scheduled in Phase 4b's `conformance/` line item. Do not tick that 4b item without it.
- [x] **Mutation-check the rows.** Done for sibling-only (restoring the crate-wide search reddens the two rule tests and both message tests) and per-controller-kind for the closure walk. **Not done for export-bypass**, because there is no export-bypass test to mutate — see the item above.
- [x] Coverage for the entry affordance semantics: exact hit, crate-wide unique bare match, ambiguity error message, and no-match.
- [x] Pin the stated invariants that currently have no test: `alias->` refs pass through the pass untouched; all four ref kinds are covered (steps, branches, outcomes, batch refs — branches and batch refs are the ones a hand-written pass forgets); the pass is idempotent (`d.c` must not become `d.d.c`, and it now runs in two places); the pass runs on **all three** load paths (a miss on the secondary or dependency path is invisible for any single-domain library); the OQ3 ruling; and that the affordance reaches a **non-exported** pipe (the twin of the export-bypass closure — the docstring claim needs enforcement).
- [x] Execution test for `batch_over` covering the derived batch code.
- [x] Coverage for both branches of the new validation message: candidate exists, and no candidate exists.
- [x] Audit existing CLI coverage for the migrated surfaces, then add a bare-code end-to-end test wherever there is not one. A perfectly-tested affordance can still be perfectly mis-called, and `pipelex which <bare_code>` is the invocation the affordance exists to preserve.
- [x] Re-run the README's demo probes (`wip/pipe-refs/probes/make-demos.sh`) and move the closures accordingly: `fallthrough` and `export-bypass` must now FAIL resolve; `ambiguous` must resolve to the own domain. Update whatever the probes/README record as expected outcomes.
- [x] Gates checklist clean (all five items).

### ⛔ CHECKPOINT C2 — MANDATORY STOP

The pipe rule is complete and self-consistent: canonical form and runtime agree, and hand-typed codes still work through a named door.

- [x] Update the Status block (OQ2/OQ3 rulings, the DRY ruling, surprises, corpus fallout).
- [x] Record status in the design doc's Phase 2 section (`build-time-qualification.md` → "Phase 2 outcome (C2)").
- [x] Update README §2's table — marked HISTORICAL with a banner rather than rewritten, and §3 gained a re-measured table.
- [x] Update the `docs/` pages that describe bare-ref resolution, pipe lookup, or the entry surfaces touched here. `docs/building-methods/libraries.md` gained a "How a pipe reference resolves" section; `docs/contribute/hub-layering.md` gained the two new hub symbols and the in-body-vs-entry guidance (that page is a drift contract target and was reviewed and acked).
- [x] Changelog entry under `[Unreleased]` noting the breaking language-behavior change. Also **removed** the superseded `[Unreleased]` entry describing the crate-wide rule this phase deletes — it never shipped, so leaving both would have published two contradictory claims.
- [x] Commit — landed on a stacked branch (PR #1092) rather than the base one, since PR #1091 carries Phase 0+1 and the two merge together.
- [x] STOP. Next session starts at Phase 3.

⚠ **These boxes sat unticked while the Status block above declared C2 passed** — caught by a PR bot, not by me. A checkpoint that reports itself complete from one place while its own checklist says otherwise is exactly the contradiction a cold-starting session cannot resolve. Tick the checklist in the same edit that updates the Status block.

---

## Phase 3 — the concept side and the footprint cleanups

Same root cause as Phase 2 — crate-wide search where owner scope was meant — but an independent surface with its own caller sweep. Kept separate so the pipe fix has a finish line that does not depend on it.

- [ ] Collapse `ConceptLibrary.get_required_concept_from_concept_ref_or_code`'s `search_domain_codes` machinery (`pipelex/libraries/concept/concept_library.py` + `concept_provider_abstract.py`) into the entry-affordance shape decided in Phase 2. Reached only from run-setup input shaping (`stuff_factory` ← `working_memory_factory` / `input_shaper` / `kernel/memory_ops`).
- [ ] **Scope the concept lookup by package, not just domain.** After resolving `alias->dep.domain.pipe`, `pipeline_run_setup` retains only `pipe.domain_code` and `pipe.code` (where it builds `search_domain_codes`), while dependency concepts are stored under `alias->domain.Concept` (by `ConceptLibrary.add_dependency_concept`). "Prefer the entry pipe's domain" therefore misses the dependency-local concept and can fall through to an ambiguous host-wide scan. Domain is not enough — the lookup needs package / child-library scope. This is the concept twin of OQ1; reuse that answer.
- [ ] Exclude aliased dependency keys from the concept crate-wide search too (same reasoning as Phase 2).
- [ ] Delete the latent defects README §4 documents: the multi-domain list dying on the first miss, and the miss escaping as the wrong exception class.
- [ ] Decide whether `pipeline_run_setup`'s own-domain-first ordering becomes meaningful or gets deleted along with the list parameter; sweep the callers (`pipeline_run_setup.py`, `runner.py`, `execution_seams.py`, `working_memory_factory.py`, `input_shaper.py`, `stuff_factory.py`, `kernel/memory_ops.py`) for the signature change.
- [ ] Relax `_pipe_codes_by_file`'s rename collision scope in `pipelex/pipeline/fixes/fix_loop.py` from crate-wide to per-domain (it can only over-block today, but it is part of the rule's footprint). ⚠ Phase 2 already corrected that function's **docstring**, whose stated justification ("`get_optional_pipe` raises on a bare code declared by two domains") stopped being true when the fall-through was deleted. The behaviour change itself is still open here.
- [ ] Tests: the resolution rows for concepts on the two-domain fixture; the ambiguity behavior settled in Phase 2; the package-scoped dependency-concept case; and two same-named pipes in different domains renaming independently after the `fix_loop` relaxation.
- [ ] Gates checklist clean (all five items).

**Carry these forward from Phase 2 — each cost real time to learn:**

- **A single-domain fixture cannot discriminate this rule.** Owner-scope and the crate-wide search agree on every input where only one domain exists, so a concept test without a competing sibling declaration passes just as happily under the rule being deleted. Mutation-check every resolution row: put the old rule back and confirm the row goes red.
- **Mutate the wiring, not just the rule.** Removing the qualification from the *dependency* load path reddened nothing in the entire suite — every other test loads a single-domain library. Assume the same blind spot exists on the concept side and go looking for it deliberately.
- **Run the whole suite, including `tests/e2e`.** Phase 2's fixture sweep collected failures from `tests/unit` + `tests/integration` only and shipped two e2e failures into a "green" checkpoint.
- **A review finding that names a file and a line is a claim to verify.** Phase 2's batched-derivation item predicted the wrong consequence, and the first test written for it passed against the bug.
- **Do not touch the working tree while `agent-test` runs**, and read the run's log rather than the harness's exit-code summary — one reported success over a log ending in `Error 1`.

### ⛔ CHECKPOINT C3 — MANDATORY STOP

The runtime is fully spec-compliant and self-consistent; only cross-repo work remains.

- [ ] Update the Status block and the design doc's Phase 3 section.
- [ ] Re-run the README's probes and demos and confirm the post-change behavior matches the design's predictions.
- [ ] Changelog entry for the concept-side behavior change.
- [ ] Commit.
- [ ] STOP. End the session. Next session starts at Phase 4a.

---

## Phase 4a — cross-repo, release-independent

These need no published `pipelex`. They can land as soon as Phase 3 is committed.

- [ ] `mthds/` — additive clarification at § *Resolution Order for Bare Pipe References*: no-fall-through is what makes `[exports]` enforceable, so the next reader does not mistake the rule for a lookup convenience. No normative change.
- [ ] Add the new hub accessor to `docs/specs/pipelex-transport-boundary.md` (workspace root). The prose spec is a doc edit; its verifying test lands in 4b, and the two must land together per the spec/conformance sync rule — so hold this until 4b is ready to go with it.

## Phase 4b — cross-repo, gated on a published `pipelex`

**Gate:** every item below needs a `pipelex` release carrying the new `interpreter_hub` accessor, installable by the sibling repo. Cut that release first. Opening these PRs beforehand produces red CI for a reason unrelated to the change.

- [ ] `conformance/` — executable conformance cases for the resolution rows (own-only, sibling-only, both-declare, nowhere) and the export-bypass closure, on a two-domain fixture. Reuse the fixture built in Phase 2.
- [ ] `conformance/` — add the new hub accessor to `tests/pipelex_transport/test_data.py` (`ALLOWED_SURFACE`), landing together with the spec doc edit from 4a.
- [ ] Run `make check-spec-links` in `conformance/` — must pass.
- [ ] `pipelex-transport/` — migrate `bridge.py`'s payload-supplied lookup to the new accessor (its code is entry-shaped; `get_required_pipe`'s pinned signature is untouched).
- [ ] `pipelex-cookbook/` — qualify the one reference that leans on fall-through: `presentation.present_as_markdown` in `examples/wip/advisory_board/bundle.mthds`. Verify the example still validates and runs against the updated runtime.
- [ ] **Error-surface sweep.** Run `make generate-error-identity` and `make generate-error-pages`, review the identity diff, and grep the TypeScript consumers for any changed or newly-introduced `error_type` literal — `mthds-starter-js/src/lib/errors.ts`, `pipelex-starter-js/src/lib/errors.ts`, `vscode-pipelex`'s `cliValidationBackend.test.ts`, and `playroom/src/app/api/graph/route.ts`. The class name is a wire string; those repos switch on the literal and fall through to a generic branch without failing to compile. No Python tool will point at this.
- [ ] Changelog entries in each touched repo noting the breaking language-behavior change, per each repo's convention (skip `wip/` docs in changelogs).

### ⛔ CHECKPOINT C4 — MANDATORY STOP (final)

- [ ] Update the Status block; all phases complete.
- [ ] Close `wip/pipe-refs/` with a final status note in the design doc and README.
- [ ] Fold the outcome into the parity track's records (`wip/parity/`).
- [ ] Commit; prepare PRs per repo as instructed by the user — do not push or open PRs without being asked.
- [ ] STOP. The work is done; anything further (release sequencing before the packaging system) is a separate track.

---

## Phase dependency map

```
Phase 0  (OQ1 gate + corpus measurement)
   |
   |  a negative OQ1 stops everything
   v
Phase 1  (extract the pass — pure refactor)          <-- safe handoff point
   |
   v
Phase 2  (flip the rule + strict lookup, together)   <-- the branch's reason to exist
   |
   +----------------------------+
   |                            |
   v                            v
Phase 3  (concept side,     Phase 4a  (mthds/ clarification —
          fix_loop)                    release-independent)
   |                            |
   +----------------------------+
                |
                v   requires a published pipelex carrying the accessor
          Phase 4b  (conformance + transport + cookbook + error sweep)
```

Lane A: Phase 0 → 1 → 2 → 3 (sequential — all touch `pipelex/libraries/`). Lane B: Phase 4a (independent once Phase 2 lands; touches `mthds/` and workspace-root `docs/specs/`). Lanes A and B share no module directory. Phase 4b joins both and is gated on a release, so it cannot run in parallel with anything.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 16 issues, 0 critical gaps left open |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** outside voice ran with repo access and surfaced findings the plan-text review could not reach — batched sub-pipe code derivation producing `domain.foo_batch`, transported `PipeFunc` carrying bare codes into the strict lookup, an undefined crate fingerprint contract, dependency concepts losing package identity, aliased dependency keys polluting the crate-wide search, and a stale `(done)` marker on the final checkpoint. All folded into the phases above.

**CROSS-MODEL:** one tension. The eng review treated the repo's written no-backward-compatibility principle as settling the breaking-change question and invested in the error message as the migration path; Codex argued the decision was unevidenced because the fall-through corpus excludes customer bundles. Resolved by holding the no-deprecation posture while adding a bounded Phase 0 corpus measurement — the principle governs whether to break, the measurement governs how well the break is communicated.

**VERDICT:** ENG CLEARED — ready to implement, starting at Phase 0.

NO UNRESOLVED DECISIONS
