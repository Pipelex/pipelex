# Deferred — a structureless concept bound to a registered class through a channel the crate cannot see

**Raised by:** the Codex reviewer on PR #1085 (P2), then **independently re-raised by cubic at P1** two rounds later against the same line. **Verified 2026-08-03**, against the tree at `d9efffbfb`, re-checked and quantified at `c4788e47b`. **Status: deferred** — no fix available at the emitter layer that is a clear win, and the correct fix is a language decision for a separate change.

⚠ **Two independent reviewers converged on this**, which raises its priority above an ordinary deferral. It is the one open question on this PR that a human should rule on. Nothing about the ruling blocks Phase 1 — but it should not sit indefinitely either.

## The shape

`ConceptFactory._handle_basic_blueprint` (`pipelex/core/concepts/concept_factory.py:386-392`) looks the **bare concept code** up in the class registry *before* falling back to the `TextContent`-based generated class. On a hit it binds the concept to that class outright — no promotion, no `refines`. What fills the registry from a user's library directory is `ClassRegistryUtils.import_modules_in_folder(base_class_names=["StructuredContent"])` + `auto_register_all_subclasses(base_class=StructuredContent)` (`pipelex/libraries/library_manager.py:338`, `:372`), so any hand-written `StructuredContent` subclass in `sys.modules` is registered under its bare name.

So a description-only concept `CustomerReview = "..."` sitting beside a hand-written `class CustomerReview(StructuredContent)` resolves, at run time, to the hand-written class.

This is not theoretical. It is **the documented endpoint of a migration guide** — `docs/building-methods/concepts/python-classes.md:162-224` teaches exactly this move ("Structure section removed — now defined in Python"), and it teaches the *bare-name* form rather than the crate-visible `structure = "<ClassName>"` one.

**Measured 2026-08-03**, and the split is what decides the trade:

| Tree | Hand-written content classes | Description-only concepts | Colliding (the shape) |
| --- | --- | --- | --- |
| `pipelex/` own test fixtures | — | — | **93** |
| `pipelex-cookbook/` | 40 | 13 | **0** |
| `pipelex-starter-python/` | 0 | 0 | **0** |

So the shape is pervasive in this repo's fixtures (e.g. `tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_2.mthds`'s `CustomerReview = "A single customer review text"` beside `pipe_sequence.py`'s three-field `CustomerReview`) — and **those fixtures are interpreted, never codegen'd**. The trees that *are* the codegen-facing examples hold none: the cookbook's structure classes all use the domain-qualified generated form, which hits the *second* lookup (`concept_factory.py:391`) and lands on the same `TextContent`-based generated class, so no divergence there.

That asymmetry is the argument for what landed. 1.2 makes the projection agree with the runtime for the plain description-only concept — common in every tree, including the 13 in the cookbook — and disagree for the registered-class shape, which does not occur in any tree that runs codegen. Reverting inverts both.

## What PR #1085 changed about it, honestly

Before, the projection emitted `StructuredContent` for every concept with no base. Because the only class reachable through the sanctioned loader path is a `StructuredContent` subclass, the old output happened to match the runtime's *nearest content ancestor* for this shape. After, it emits `TextContent`, which does not.

But the projection was never the runtime class either way: it emits a **fieldless shell with `extra="allow"`**, before and after. The runtime class carries the author's real fields and validators. Keeping the base would not have made the projection usable as a stand-in — that needs the whole class body, which the crate structurally cannot supply.

The ledger, stated in full rather than in the direction that flatters the PR:

- **Worse.** The declared base no longer matches, and `TextContent.text` is required (`pipelex/core/stuffs/text_content.py:17`), so `Projected.model_validate({"title": …})` now *fails* where the old shell absorbed the payload into `extra`.
- **Better.** The old projected `X(StructuredContent)`, if `structures.py` lands in the library directory, is itself auto-registered and can **win the registry over the author's real class** (`auto_register_all_subclasses` is first-wins, `pipelex/system/registries/class_registry_utils.py:167-170`) — silently substituting an empty shell for a three-field class. The projected `TextContent` subclass is never registered at all, so that hazard is gone.
- **Unchanged.** The interpreted library. Nothing in the runtime consumes the projected class, so "the projection silently changes object content into text content" overstates the blast radius.

Net: the PR **moves an already-divergent case from "right base, empty body" to "wrong base, empty body"**, and removes a collision hazard on the way. It does not introduce the divergence.

## Why it is not fixed here

Three candidates, none a clear win:

1. **Revert 1.2 to `StructuredContent`.** Re-breaks the common case — every description-only concept with no hand-written class, which is the majority everywhere and the entirety of the cookbook — and reinstates the registry-clobber hazard. Strictly worse.
2. **Teach the crate the auto-detected class.** The crate builder would have to consult the live class registry — `get_class_registry()` returns the active library's ContextVar-scoped registry when one is set and the process-global one otherwise — making the crate *and its fingerprint* depend on what happened to be importable in the emitting process. (The scoping isolates concurrent runs from each other; it does nothing to make the registry's *contents* reproducible, which is the property at stake here.) That destroys the two properties the crate exists for: portability (it travels to a sandbox as `python_sources`) and a semantic fingerprint the stamp/lock trust chain rests on. A contract break, not a layering nit.
3. **Drop the bare-name auto-detect at `concept_factory.py:389`, requiring the explicit `structure = "<ClassName>"` form.** This is the *actually correct* resolution: it makes the runtime's binding crate-visible, collapses the case into the already-handled `opaque_python_class` branch, and removes an environment-dependent name binding. Breaking changes are fine in this repo. But it is a language/runtime decision that contradicts a published migration guide and touches many fixtures — far outside "small and obviously correct", and outside this PR's scope.

## What settling it will need

- A ruling on (3): should a hand-written class have to be *named* in the `.mthds` to bind, or should a bare-name match keep working? Same family of question as D-1's `domain_hint` — a language call, not a codegen one.
- Either way, `docs/building-methods/concepts/python-classes.md:218-221` currently teaches the form that is invisible to codegen. That doc/feature tension needs resolving whichever way the ruling goes.
- **No test covers this shape today**, for either reader. `test_projection_agrees_with_runtime_base.py` builds its four shapes against an *empty* library, so `concept_factory.py:389` is never taken. Whoever settles this should add the missing coverage as part of it — the branch that binds a concept to a registered class is currently unguarded on both sides.
