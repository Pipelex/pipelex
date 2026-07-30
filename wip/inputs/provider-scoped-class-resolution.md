# The concept provider does not carry its own class registry

**Status:** deferred — a real architectural gap with no reachable failure today. Raised by Codex (P1) on PR #1072 (`refactor/Concept-purity`), verified, and declined for that PR. What it *did* change is the branch's own wording: three places claimed a scoping property the code does not deliver, and those were corrected.

## The claim

`ConceptLibrary.get_structure_class` resolves through `get_class_registry()`, which selects a registry from the **current async context**, not from `self`. So passing a specific `ConceptLibrary` as `concept_provider` does not actually scope class resolution to that library: if a caller hands over library A while the context names library B, resolution follows B. Codex's proposed fix was to store or inject the library's registry resolver on the provider.

## Verified: the mechanism is real

- A `ConceptLibrary` **holds no registry**. The per-library `ClassRegistry` lives on `Library` (`libraries/library.py`, `_class_registry` private attr with `get_class_registry` / `set_class_registry`); `ConceptLibrary` is a plain field of `Library` with no back-reference, and `ConceptLibraryAbstract` declares no registry member. So "use `self`'s registry instead" is not a correction — there is nothing to use.
- Scoping runs `get_class_registry()` → `class_registry_scoping.resolve()` → the resolver `set_interpreter_hub` installs → `_resolve_scoped_class_registry`, which reads the `_library_id` ContextVar and asks `LibraryManager.get_library_class_registry`. Unset, or a library with no registry of its own, falls back to the process-global Kajson registry.

## Verified: the divergence is not reachable

**Provider-library and registry-library are two reads of one variable.** Every non-forwarding `concept_provider=` source in `pipelex/` is `get_concept_library()`, which is `get_interpreter_hub().get_library().concept_library` → `LibraryManager.get_current_library()` → the same `_library_id` ContextVar that `_resolve_scoped_class_registry` reads. They cannot name different libraries.

**The one place that installs a per-library registry pairs the two.** `runtime_bridge/primitives/rehydration.py` calls `library.set_class_registry(run_registry)` and `set_current_library(library_id=library_id)` in adjacent statements on the same library. Every other `set_class_registry` call is a test, and the integration fixture (`tests/integration/pipelex/fixtures/pipe_job_helpers.py`) pairs them the same way.

**The only non-hub provider deliberately depends on the ambient read.** `cli/commands/run/_run_core.py`'s `--save-csv` step uses `ConceptLibrary.make_empty()` *after* the run library is torn down, precisely so the lookup lands on the process-global registry that still holds the generated classes. Codex's fix would break that site — an empty library has no registry — unless it re-derived the global fallback `get_class_registry()` already implements. The branch's own boot-free tests depend on the same decoupling.

That is why the fix was declined: no reachable failure motivates it, it would require inventing a registry for every parentless `ConceptLibrary`, and it would end up re-implementing the fallback it replaced. Also worth noting it is **not a regression** — on `dev`, the removed `Concept.get_structure_class()` and `Concept.are_concept_compatible` called `get_class_registry()` from the same module. PR #1072 moved *where* the call lives, never *which* registry it reads.

## What was actually wrong, and was fixed

The branch asserted a scoping property in three places. Two were docstrings written in this PR — `class_registry_access.py` ("scoped to the library you asked rather than to whatever the ambient registry happens to hold") and `stuff_spec.py` ("the rendering can no longer read whatever the ambient registry last held") — and one was the PR body's defect #3. All three overstated: the ambient read left the *wire model*, and gained a single implementation behind one seam, but it is still ambient. `class_registry_access.py`'s docstring is the module's stated architectural rationale, so a reader would have taken it as a guarantee. Corrected in the same PR.

## Trip-wires — any one of these makes it real

1. A caller passes `library_manager.get_library(library_id=X).concept_library` as the provider instead of `get_concept_library()`.
2. A **dependency/child** library's `concept_library` is used as a provider. Child `Library` objects live in `Library.dependency_libraries` and are *not* in `LibraryManager._libraries`, so `get_library_class_registry` structurally cannot see their registry. Today only the cross-package `_concept_resolver` touches them, never `get_structure_class`.
3. `InterpreterHub.set_concept_library` gains a live writer (it currently has **zero** callers, so its standalone-library fallback branch is dead).
4. A `set_class_registry` call site appears that is not paired with `set_current_library` on the same library.

## The shape of the fix, if it ever lands

Give `ConceptProviderAbstract` a way to name its registry and have `ConceptLibrary` carry the one from its parent `Library`, falling back to `get_class_registry()` when it has no parent — which keeps `make_empty()` and the `--save-csv` path working. One place changes (`ConceptLibrary.get_structure_class`), which is the property the single-seam refactor bought even though it did not use it.

## Related, from the same PR's finalize review

Four items surfaced alongside this one. All are design tradeoffs or pre-existing asymmetries rather than defects, and all share the same reachability gate as the note above.

**The `StuffContent` bound changed the compatibility verdict path too, not just `get_structure_class`.** `ConceptLibrary` resolves with `get_required_subclass(base_class=StuffContent)`, where the old class tier used an unbounded `get_class`. A name registered as a *non*-`StuffContent` class used to flow into `are_classes_equivalent` / `issubclass` and could answer `True`; it now raises. That tightening is deliberate and pinned for `get_structure_class` (`test_get_structure_class_rejects_a_class_that_is_not_stuff_content`), but only the `get_structure_class` half was written down — the compatibility half rides along undocumented. Same unreachability argument applies (the factory refuses to build such a concept), which is why it was recorded rather than reverted.

**`StuffSpec.render_stuff_spec` does not consult `declares_a_structure_class`.** An input declared `native.Anything` raises on the render/template paths while `is_compatible` answers `False` for it. Not a regression — the base commit raised `ConceptValueError` at the same point — but the new property makes the asymmetry visible for the first time. Whether rendering *should* have an `Anything` arm is a real question; it is not this branch's.

**`template_image_analyzer`'s dotted-path branch resolves unconditionally** while the two single-variable branches now answer for `Anything`. So `{{ anything_var }}` is fine and `{{ anything_var.field }}` fails bundle load. Pre-existing in kind, surfaced by the same property.

**`pipe_abstract` is a second read-side resolution, with a weaker bound.** It uses the lenient `get_class` (no `StuffContent` bound, `None` rather than a raise) rather than the provider seam, because importing either hub there is a pyright cycle. Deliberate — the schema is optional decoration on a graph-registry entry — and the honest resolution was to say so in `class_registry_access.py`'s docstring rather than change the code. Worth revisiting only if that module ever escapes the cycle.
