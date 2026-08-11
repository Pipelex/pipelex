# Decided design: in-body references qualify at build time

**Status.** Decided 2026-08-11, not yet implemented. This settles the two questions [README.md](README.md) left open: the **direction** — tighten the runtime to the MTHDS standard's resolution rule — and the **mechanism** — qualify in-body references once, at library build time, rather than threading the caller's domain through the lookup API. The README carries the evidence for the direction (the export bypass, the corpus measurement, the concept-side defects); this document records the mechanism, why it won, and the implementation plan.

## The decision in one paragraph

Bare in-body references (pipe steps, branches, outcomes, batch refs, concept I/O refs) are qualified to their **owner domain** when the library is built, exactly as the standard's resolution order prescribes and exactly as `_qualify_concept_ref` in the crate normalizer already does. After the build, the live library only ever sees fully-qualified in-body refs, so lookups are direct key hits and the resolution rule lives in one shared function instead of at every call site. The crate-wide bare search survives only as an explicitly-named **entry-point affordance** for user-supplied codes (`pipelex run my_pipe`, CLI commands, API payloads), which is outside the standard's scope — the standard governs references written in bundles, not what a user may invoke by hand.

## Why build-time qualification won over domain-threading

Three facts, established by reading the code after the README was written:

1. **The ordinary load path already builds a `LibraryCrate`.** The README worried that the run path "does not normalize" and any normalizer-based fix would have to deal with that first. In fact `library_manager` assembles a crate from the parsed blueprints (`LibraryCrateFactory.make_from_blueprints`) on every load path — main, secondary, and dependency loads — and builds each pipe by iterating `crate.pipes`, already asserting the keys are domain-qualified, before calling `PipeFactory.make_from_blueprint` with the owner `domain_code` in hand. What the run path skips is the *normalization pass over that crate*, not the crate itself. The insertion point exists.
2. **Concepts already follow the spec rule at build time — pipes are the one anomaly.** `PipeFactory.make_from_blueprint` rejects any bare input/output concept ref that is not native or declared in the pipe's own domain, and `StuffSpecFactory` builds the stuff spec against the owner domain. This is why the corpus probe found zero cross-domain bare concept refs anywhere: the build refuses them. Sub-pipe refs are the outlier — `SubPipe.pipe_code` stores the authored string verbatim and resolves it lazily, crate-wide, on every lookup. The change is therefore "make pipe refs do what concept refs already do", not a new architectural layer.
3. **`get_required_pipe(pipe_code)` is part of the pinned transport boundary.** It is listed in `conformance/tests/pipelex_transport/test_data.py` (`ALLOWED_SURFACE`) and called by `pipelex-transport/bridge.py` with a payload-supplied code. Threading a caller-domain parameter through the hub accessors changes that pinned signature and drags the transport spec/conformance pair into the change. Build-time qualification leaves the signature untouched: in-body refs stop needing the fallback because they arrive qualified, and the bridge's call — a payload-supplied code — is an entry-point lookup anyway.

Domain-threading loses on every axis examined: it changes a Protocol, the `interpreter_hub` free functions, and a transport-pinned signature; it keeps authored bare refs live at run time and re-resolves them (with a full library scan) on every lookup; and it distributes the resolution rule across every present and future call site, so the normalizer and the runtime agree by discipline rather than by construction. No scenario was found where threading holds an advantage — the one that would (no crate on the load path, refs needed in authored form at run time) turned out not to exist.

## The design

### One shared qualification pass

Extract the in-body reference qualification step out of `crate_normalization.py` (the application of `_qualify_pipe_ref` / `_qualify_io_ref` inside `_normalize_pipe`, plus the concept-side qualification) into a standalone pass over a `LibraryCrate`, and change the pipe rule from crate-wide search to **owner-domain qualification** — the exact twin of `_qualify_concept_ref` sitting beside it. Both consumers call the same function:

- `normalize_crate` (the `resolve` / `codegen` / `build` paths) — unchanged in shape, now spec-compliant in rule.
- The library build in `library_manager` — the pass runs on the crate before pipes are constructed, on **all** crate→pipes paths (main load, secondary loads, dependency-package loads).

The normalizer and the live library then cannot disagree about what an authored reference means, structurally rather than by mirrored implementations — the parity track's goal achieved by construction. Note that owner-domain qualification implements the standard's full resolution order on its own: existence is checked afterwards by the ordinary dependency validation, so "bare `foo` from domain `alpha` when only `beta.foo` exists" qualifies to `alpha.foo` and then fails validation with a missing-pipe error, which is exactly the standard's step 3.

Cross-package refs (`alias->…`) are left intact by the pass, as the normalizer already leaves them — canonical cross-package resolution is the packaging project's design work (see the sequencing section).

### The library lookup becomes strict; entry lookups get a named affordance

- `PipeLibrary.get_optional_pipe` drops its step-3 bare-code crate-wide fallback (and with it the `domain_hint` TODO — [d1-domain-hint-deferred](../parity/d1-domain-hint-deferred.md) closes as subsumed). What remains: direct key lookup and the cross-package (`alias->`) handling.
- The crate-wide unique-match search moves to a separately-named entry affordance on the library (working name `find_pipe_by_bare_code`; final name to be settled at implementation), exposed through a new `interpreter_hub` accessor. Its semantics: exact ref hits directly; a bare code matches crate-wide; ambiguity raises an error that asks the user to qualify. Its docstring states explicitly that it deliberately does **not** consult `[exports]` — a user invoking a pipe by hand is not an in-body reference, so package visibility does not apply.
- The genuinely entry-shaped call sites migrate to it: the CLI commands (`which`, `show`, `validate`, the `build`/`codegen` groups), `pipeline_run_setup`, the builder operations, and `pipelex-transport`'s bridge. Everything else — controllers, `sub_pipe`, `signature_walk`, `library` validation — looks up refs that are stored on built objects, which arrive qualified after this change, and needs no edit at all.
- **Transport boundary:** adding the new hub accessor is an additive change to the pinned surface. Update `docs/specs/pipelex-transport-boundary.md` and `conformance/tests/pipelex_transport/test_data.py` (`ALLOWED_SURFACE`) in the same change, per the spec/conformance sync rule. `get_required_pipe`'s signature does not move.

### The concept side

- `ConceptLibrary.get_required_concept_from_concept_ref_or_code`'s `search_domain_codes` machinery serves only user-supplied codes during run-setup input shaping (`stuff_factory` ← `working_memory_factory` / `input_shaper` / `kernel/memory_ops`) — in-body concept refs never reach it after (indeed, already before) this change. Collapse it into the same entry-affordance shape: prefer the entry pipe's domain, else crate-wide unique match. This deletes the two latent defects the README's §4 documents (the multi-domain list dying on the first miss, and escaping as the wrong exception class) and either makes `pipeline_run_setup`'s own-domain-first ordering meaningful or deletes it along with the list parameter.
- README §8's open question 3 answered itself during this investigation: sub-pipes in non-entry domains cannot hit a bare-concept path at run time, because their concept refs were qualified (or rejected) at build. The defects are confirmed latent, entry-only.

### Consequences inside this repo

- **Perf**: the removed fallback scanned every library entry per bare lookup at execution time; qualified refs are dict hits.
- **`fix_loop._pipe_codes_by_file`** blocks renames on cross-domain code collisions because the library raises on them; under the spec rule the collision scope shrinks to the domain. Relax it in the same change — it can only over-block today, but it is part of the rule's footprint.
- **Tests that pin the crate-wide rule flip** (they are correct tests of the old rule; they become tests of the new one): `test_crate_normalization.py::test_bare_cross_domain_pipe_refs_resolve_to_the_declaring_domain`, `test_pipe_library_lookup.py::test_bare_code_ambiguous_raises` and `::test_bare_code_unambiguous`. Tests that construct pipes directly with bare sub-refs (bypassing the crate pass) need their refs qualified once the strict lookup lands.
- **User-facing surfaces that echo refs** (errors, graphs, `show`) print qualified refs where the author wrote bare — same as the normalized crate already does; arguably clearer.
- **New conformance-shaped unit coverage** in this repo: the four corpus rows (own-only resolves; sibling-only errors; both-declare resolves to own; nowhere errors) plus the export-bypass closure.

## Deliberate non-goals

- **No full normalization on the load path.** Refinement flattening, native expansion, and string-concept materialization stay crate-only — running them at load would change live library semantics and is not needed for this fix. Only the qualification step is shared.
- **No cross-package resolution design.** `alias->` refs stay untouched; how a cloned remote package's refs are addressed, folded, and fingerprinted is the packaging project's own question. This change clears the ground so that is the *only* open resolution layer left.
- **No `mthds/` normative change.** One additive clarification only (see the cross-repo set).

## Why this sequences before the packaging system

The upcoming remote-methods system (GitHub addressing, cloning, version management, integrity checksums) depends on properties the current rule destroys and the spec rule provides:

- **Checksums and lockfiles need a package's meaning to be a function of its content.** Owner-domain qualification makes resolution a local computation — bundle plus its domain — so the publisher's normalized crate and fingerprint equal what any consumer computes, regardless of install context. Crate-wide resolution makes meaning depend on the merge unit: the same file can resolve differently, or stop loading, depending on its neighbors, which is fatal for content-addressed integrity. And once lockfiles pin fingerprints in the wild, changing the canonical form invalidates all of them — settle it first.
- **Installing a package must never change the meaning of methods already present.** The standard's conflict rule (different domains, same code — no conflict) is what makes composition scale. The current rule inverts it: every added package raises the probability that an unrelated bare ref becomes ambiguous and a working method stops loading, and that failure mode grows with exactly the dimension a catalog is built to grow. After this change, installing a package can affect at most a bare CLI invocation (contained, asks to qualify), never the execution of a loaded method.
- **`[exports]` becomes the versionable API contract.** Semver-style reasoning about method packages needs an enforceable boundary for "what may a consumer depend on". The measured export bypass means that boundary is currently fiction. Closing it while the migration cost is one reference is cheap; closing it after unknown remote consumers lean on fall-through is the ecosystem break the original deferral feared. The cost of tightening is at its all-time minimum and only grows.
- **Remote execution threads less context.** With lazy bare refs, executing a dependency's pipe correctly needs the caller's domain *and* package carried into every lookup. With refs qualified at load, the domain half is baked into the stored ref; only the package scope remains, which is what `alias->` already expresses.

## Cross-repo set (land as one coordinated change)

- `conformance/` — executable cases for the four resolution rows and the export-bypass closure (the case nobody would think to write without the visibility argument), plus the additive transport-surface update.
- `pipelex-cookbook/` — qualify the one reference that leans on fall-through: `presentation.present_as_markdown` in `examples/wip/advisory_board/bundle.mthds`.
- `mthds/` — **last**, per the ordering noted in [deferred-review-observations](../parity/deferred-review-observations.md) §4: an additive clarification at § *Resolution Order for Bare Pipe References* saying that no-fall-through is what makes `[exports]` enforceable, so the next reader does not mistake the rule for a lookup convenience.

## Open questions to settle during implementation

1. **Dependency-pipe lookup scoping today. — ANSWERED 2026-08-11, GO.** Measured with [`probes/dep-subpipe-scope.py`](probes/dep-subpipe-scope.py). The execution-time lookup consults the **host** library unconditionally (`sub_pipe.py` → `interpreter_hub.get_required_pipe` → the ambient current library); there is no child-library scoping on that path, and the host's bare-code fall-through explicitly skips `alias->` entries. So a dependency's own bare sub-pipe ref never reaches the dependency's own pipe: with a plain host the package **fails to load**, and with a host that happens to declare the same bare code it loads and **silently binds the host's pipe**. In the shape a package actually ships — a manifest `[exports]` naming only the entry pipe — it fails earlier and for a second reason: the export filter drops the authored helper from the dependency's own child library, carving out only *synthetic* helpers. That is a pre-existing defect, written up in [dependency-subpipe-scope-deferred.md](dependency-subpipe-scope-deferred.md) and deferred to the packaging project — the fix needs package scope threaded through the lookup **and** export filtering that carries authored helpers, neither of which this change designs.

   The go/no-go turns on whether owner-domain qualification makes that worse, and it does not. The qualified ref (`dep_domain.helper`) resolves to `None` in the host exactly as the bare one does, so nothing regresses; the silent host-capture becomes a deterministic not-found naming the scope that should have been searched; and once the lookup is package-scoped, a qualified ref is a direct key hit in the child library, whose own keys are already `dep_domain.helper`. **Proceed.** The Phase 2 item "run the pass on the dependency load path" must not be read as making dependency sub-pipe refs resolve — it cannot, until the lookup is package-scoped.

   **Ordering constraint this measurement imposes on Phase 2.** `Library.validate_pipe_library_with_libraries`'s first loop looks up a **bare** sub-pipe code against the child library, whose keys are qualified — so that lookup is served today *only* by the crate-wide fall-through the strict lookup deletes. Running the pass on the dependency load path and deleting the fall-through therefore have to land in the same change; that co-landing is also what makes "`library` validation needs no edit" true.
2. **Final name and exact semantics of the entry affordance** (one method or a required/optional pair; where the ambiguity error message lives).
3. **Whether `get_optional_pipe` keeps the cross-package bare-remainder search** (step 2's `alias->` + bare code). It is alias-scoped, so it does not reopen the cross-domain hole; leaning toward keeping it until the packaging design rules on cross-package reference forms.

## Implementation phases

The executable plan — phases, checkpoints, and per-phase task lists — lives in [../../TODOS.md](../../TODOS.md) and is the plan of record. It was restructured after the engineering review into C0–C4, splitting what this document originally described as one "Phase 1" into a pure-refactor extraction (Phase 1) and the rule flip (Phase 2), so that no checkpoint rests on a tree where the normalizer and the live library disagree. Do not maintain a second phase list here; record **outcomes** below as each checkpoint passes.

### Phase 1 outcome (C1)

**The extraction landed, behavior-identical except for one deliberate change.** The in-body qualification step now lives in `pipelex/libraries/crate_qualification.py` as `qualify_crate(crate) -> QualifiedCrateContent`, and `normalize_crate` consumes it. The rule is unchanged: bare pipe refs still resolve crate-wide.

Equivalence was established by running the committed implementation (loaded from HEAD) beside the working-tree one over the same inputs and comparing the full serialized output, not just the fingerprint:

- every crate buildable from this repo's `.mthds` files — identical, including the crates that raise;
- ten hand-built crates covering what the repo corpus cannot reach — identical, including all four error paths (ambiguous ref, unresolvable ref, unqualified concept key, unqualified pipe key).

The harness was then mutation-checked, because a comparison that is green on its first run proves nothing. Dropping structure-field qualification turns one case red; applying the Phase 2 owner-domain rule turns three red. Both mutations were reverted and the tree confirmed byte-identical.

**The exception: error precedence between two independent defects.** Qualification now runs as one complete phase ahead of refinement flattening, where HEAD interleaved them (concepts → flatten → pipes). A crate carrying *both* a refinement cycle and an ambiguous bare pipe ref used to report the cycle and now reports the ref.

The differential harness above could not have found this, and it is worth being precise about why: every crate it compares carries at most one defect, so a precedence change between two error paths is invisible to it by construction. The finding came from review. Phase 2 moves considerably more error surface, so its own equivalence checks need at least one multi-defect input.

Accepted rather than fixed. Restoring the old order would mean splitting the pass into a concept half and a pipe half so the normalizer could interleave them — which contradicts "one shared qualification pass" and buys nothing, because Phase 2 runs the pass with no flattening at all. Both errors are `CrateNormalizationError`, the crate is invalid either way, and which of two independent defects is named first is not a contract. It is recorded in `normalize_crate`'s docstring so the next reader meets a decision rather than a surprise.

**The corpus cannot see the Phase 2 flip.** That second mutation *is* the rule Phase 2 installs, and against all 54 crates built from this repo it produces byte-identical output. Every bare in-body pipe ref in this repo already resolves within its own domain. This is exactly the trap the plan's two-domain-fixture item names, now measured: a test grounded in this repo's bundles passes identically under both rules, so the discriminating fixtures must be hand-built and mutation-checked.

**Fingerprint / envelope ruling — the pass does not deal in fingerprints at all.** `qualify_crate` returns a `QualifiedCrateContent` NamedTuple carrying the rewritten `concepts` and `pipes`. It takes a crate and returns content.

The first cut returned a `LibraryCrate` with the envelope carried over verbatim and a paragraph of module docstring explaining why the `fingerprint` it handed back described pre-qualification content. The reasoning was sound as far as it went — a crate does not record which of the two digest schemes produced its value (`compute_fingerprint_from_content` for a merged crate, `compute_normalized_fingerprint` for a normalized one), so the pass cannot recompute correctly and must not guess. But the conclusion was wrong: a return type that needs a paragraph of excuse is the wrong return type. `LibraryCrate.fingerprint` documents itself as "SHA-256 hex digest of the serialized concepts + pipes content", and handing back a crate that violates its own field docstring is a trap for whoever reads it next.

Returning the two mappings makes the contradiction unrepresentable, and it costs the callers nothing — both of them already hold the crate they passed in, so the envelope is right there, and `normalize_crate` constructs a fresh crate anyway. Phase 2's `load_from_crate` keys idempotency on the **incoming** crate's fingerprint, which is what external callers pass to `is_crate_loaded`; nothing downstream ever wanted a fingerprint from the pass. It also dissolves a second issue for free: with no envelope to carry, there is no question of whether `source_map` / `domains` / `python_sources` come back aliased or copied.

The neighbouring bug this originally guarded against is unaffected and still real: `normalize_crate` builds its result field by field and drops `python_sources` (deferred, [normalize-crate-drops-python-sources-deferred.md](normalize-crate-drops-python-sources-deferred.md) — the one-line fix moves customer Python source into a CLI stdout stream and an HTTP response body, which is a disclosure decision, not a typo correction).

**A test-design trap worth carrying into Phase 2.** The pass's own test module was first written around a fixture full of bare refs, asserting the envelope, non-mutation, and idempotency — and every one of those tests passed against a `qualify_crate` replaced by a no-op, because none of them read a ref *out of the result*. The envelope looked right, the input was untouched, and two no-ops compared equal. The rule itself was covered (a no-op reddens fifteen tests in the normalizer suite), so nothing was actually unguarded — but the module that existed to state the pass's contract could not tell the pass from a stub. It now reads a qualified ref back out in every test, and a no-op reddens twelve of fourteen.

The shape of that mistake — a fixture rich enough to look thorough, assertions that never touch the transformed value — is exactly what Phase 2's resolution-row tests are exposed to, on top of the single-domain blindness already noted. Both are only caught by mutating the thing under test.

**Consumer inventory:** [normalized-crate-consumers.md](normalized-crate-consumers.md). The headline is that the plan's worst case does not exist — nothing writes a normalized crate back over a `.mthds` source file. `pipelex fix` rewrites user files but never through a crate, and no fix op writes a pipe ref at all (a property Phase 2 should re-check rather than assume). What does move is the stamped `codegen.lock` fingerprint, on every committed projection.

**Observation for a later phase, not acted on:** `_qualify_io_ref`'s cross-package guard appears unreachable through a constructed blueprint — the io-ref validator rejects `alias->domain.Concept` in `inputs` and `output` outright. The guard is preserved verbatim by this refactor; whether it is genuinely dead is a question for the phase that owns cross-package reference forms.
