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

1. **Dependency-pipe lookup scoping today.** Dependency pipes are keyed `alias->domain.code` in the host library, and `library.py` consults per-dependency child libraries during validation. Establish precisely which library a dep pipe's lazy sub-pipe lookup consults at execution time, and confirm the qualified refs produced by the pass resolve correctly in that scope. This is a pre-existing question the packaging work needs answered regardless; qualified refs make it strictly easier.
2. **Final name and exact semantics of the entry affordance** (one method or a required/optional pair; where the ambiguity error message lives).
3. **Whether `get_optional_pipe` keeps the cross-package bare-remainder search** (step 2's `alias->` + bare code). It is alias-scoped, so it does not reopen the cross-domain hole; leaning toward keeping it until the packaging design rules on cross-package reference forms.

## Implementation phases

**Phase 1 — the shared pass and the normalizer.** Extract the qualification step from `crate_normalization.py` into a standalone crate pass; switch the pipe rule to owner-domain; `normalize_crate` consumes it. Flip the normalizer tests. The README's demo closures move accordingly: `fallthrough` and `export-bypass` must now fail resolve, `ambiguous` must resolve to the own domain.

**Checkpoint C1** — a coherent unit: the canonical form is now spec-compliant everywhere the crate is produced, while the live library still runs the old rule (a temporary, known reader divergence — do not stop here longer than necessary). Record status, surprises, and any corpus fallout in this doc before continuing.

**Phase 2 — the live library.** Run the pass on all crate→pipes paths in `library_manager`; strip the bare fallback from `get_optional_pipe`; add the entry affordance and its hub accessor; migrate the entry-shaped call sites; collapse the concept-side `search_domain_codes` machinery; relax `fix_loop`'s collision scope; flip the library lookup tests; add the resolution-row and export-bypass unit coverage. `make agent-check` and full `make agent-test` gate the phase.

**Checkpoint C2** — the runtime is fully spec-compliant and self-consistent; only cross-repo work remains. Record status here, re-run the README's probes and demos, and update the README's §2 table (it describes the pre-change state and becomes historical at this point).

**Phase 3 — the coordinated cross-repo set.** Conformance cases + transport-surface update (spec and `ALLOWED_SURFACE` in the same change, `make check-spec-links`), the cookbook qualification, then the `mthds/` clarification last. Changelog entries note the breaking language-behavior change per repo convention.

**Checkpoint C3** — done; close this wip folder with a final status note and fold the outcome into the parity track's records.
