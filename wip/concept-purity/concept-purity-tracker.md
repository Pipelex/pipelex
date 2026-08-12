# Concept purity — evicting the ambient class-registry reads from the core concept model

**Reviewer's guide**, archived from the repo-root `TODOS.md` once PR [#1072](https://github.com/Pipelex/pipelex/pull/1072) was finalized. Branch `refactor/Concept-purity`, cut from `dev` at `ed7435a7c`. Two functional commits: `e94b2a4c9` (compatibility) and `89cf2158d` (class access, purity lock, docs); the rest are review-round corrections. This document is what the branch is *for* — read it before the diff.

**Lineage:** continues the hub-split / layer-placement line of work (#1062, #1064, #1070, #1071) — same doctrine, applied to the last ambient lookup left inside the core concept model.

## The problem in one paragraph

`Concept` (`pipelex/core/concepts/concept.py`) is a subclass of the MTHDS-protocol wire model `ConceptAbstract` — `code`, `domain_code`, `description`, `structure_class_name: str`, `refines`. Pure serializable data. Except that four of its members answered *behavioral* questions by reaching into the process-global class registry, and that one import is what `system/registries/class_registry_access.py`'s own docstring cited as the reason the accessor has to sit below both hubs. It coupled a standard-owned wire model to a Pipelex process-global — the model could not answer a question about itself without a Pipelex runtime having been booted around it, and every caller that held a `Concept` inherited that dependency invisibly.

## What changed

**Compatibility is now two tiers, composed by the thing that owns resolution.**

- `Concept.are_compatible_by_declaration` is the *declaration tier*: pure over the model's own fields plus an injected `concept_resolver` — dynamic short-circuits, ref equality, declared-class-name equality, `refines` chains including cross-package aliases. No registry.
- `are_structure_classes_compatible` (`tools/typing/class_utils.py`) is the *class tier*: pure over two already-resolved classes — equivalence, then (loose only) subclass or nested-field.
- `ConceptLibrary.is_compatible` composes them. Declaration tier first; classes are resolved only when it is inconclusive.

The verdicts are asymmetric on purpose, and the docstrings say so: at the declaration tier, `True` means "established by the declarations" and `False` means "*not established at this tier*" — never "incompatible".

**Class access left the model.** `ConceptProviderAbstract` grew `get_structure_class(concept)`, implemented by `ConceptLibrary` against the active registry with a `StuffContent` subclass bound.

| removed from `Concept` | replaced by |
| --- | --- |
| `are_concept_compatible(..., strict=)` | `are_compatible_by_declaration` + `are_structure_classes_compatible`, composed by `ConceptLibrary.is_compatible` |
| `get_structure_class()` | `ConceptProviderAbstract.get_structure_class(concept=…)` |
| `is_valid_structure_class(name)` | a private module-level helper in `concept_factory.py`, its only caller |
| `search_for_nested_image_fields_in_structure_class()` | compose the provider with the existing free `search_for_nested_image_fields` |

`render_concept_representation` now takes the already-resolved `structure_class`. `StuffSpec.render_stuff_spec`, `InputStuffSpecs.build_inputs_template` and `render_inputs` take a `concept_provider` and resolve once.

## Three defects this closes

1. **Cross-package `refines` silently failed to resolve at five call sites.** `pipe_llm` (×2), `template_image_analyzer` (×2) and `template_document_analyzer` compared two `Concept` values directly instead of going through `ConceptLibrary.is_compatible`, so `concept_resolver` was `None` and a `dep->domain.Code` alias never resolved. Wrong compatibility verdicts at authoring time and on the PipeLLM text-vs-object run branch. Every other compat check in the tree already went through the wrapper. One of the five is pinned by `tests/unit/pipelex/pipe_operators/pipe_llm/test_template_image_analyzer_cross_package.py`, which drives the *public* `analyze_template_for_images` rather than a private resolver; the other four are the same one-line swap through the same wrapper.

2. **An unresolvable structure class answered `False` instead of failing.** "Unknown" and "incompatible" are different answers; conflating them is a latent wrong-verdict bug. It now raises `ConceptStructureClassNotFoundError` — a `ConceptValueError` subclass, so guards that already convert that error at their own boundary keep working unchanged.

3. **The ambient read left the wire model.** `Concept` reads no registry at all, and the declaration tier answers compatibility without resolving a class in the first place — so concepts whose structure classes were never materialized still get an answer. Class resolution still goes through the process's *active* registry rather than one the provider carries; what changed is that it now has exactly one implementation, behind `ConceptProviderAbstract`. See "the scoping half is not done" below for what that does and does not buy.

## Where to look, and what to check

- **`pipelex/core/concepts/concept.py`** — the point of the branch. It should import nothing from `system/registries/`, and every remaining member should be a function of the model's fields (plus the injected resolver or the passed-in class).
- **`pipelex/libraries/concept/concept_library.py`** — `is_compatible` and `get_structure_class`. This is the one place that legitimately owns resolution; check the composition order and the `declares_a_structure_class` guard.
- **The five former bypass sites** — check that direction and `strict` semantics survived the move. `is_image`/`is_document` are `strict=True`; `has_nested` is `strict=False`.
- **`tests/unit/pipelex/core/concepts/test_concept_registry_boundary.py`** — the golden set that keeps this from growing back. It matches the accessor by import name, by module path, by attribute call (`runtime_hub.get_class_registry()`), and via the two indirect roots that bypass the accessor entirely (`KajsonManager`, `ClassRegistryUtils`) — an import-name-only walk would have waved all three through.

## Decisions a reviewer will want the reasoning for

**`native.Anything` declares no structure class at all, and that is not a missing registration.** `NativeConceptCode.ANYTHING.structure_class` is `None` by design (it is the untyped vehicle), while `structure_class_name` still derives `"AnythingContent"` mechanically — a name no registry ever holds. The old silent-`False` was masking that: `is_compatible(Anything, Text)` answered `False` for the *wrong reason*. `NativeConceptCode.is_structureless_concept` + `Concept.declares_a_structure_class` make "this concept has no structure" a declared property, and `is_compatible` returns `False` for it before reaching the class tier. Verdicts unchanged; the reasoning is now correct.

**`pipe_machinery/pipe_abstract.py` reads the class registry directly, and must.** Importing either hub there is a pyright `reportImportCycles` failure via `runtime_hub` → `plugins.orchestrator_registry` → `pipe_run.pipe_job` → here, and a *deferred* import does not help: the error is reported at `interpreter_hub.py`, where no line-level ignore can reach. That is exactly what the below-both-hubs accessor exists for. Note the constraint is a **static-analysis** cycle, not a runtime one: those edges are `TYPE_CHECKING`-only and a clean-interpreter probe shows all three modules absent from `runtime_hub`'s runtime closure — but pyright counts them, and the finalize review caught the first draft of this comment stating it as a runtime closure. The docstring now records the measurement. Two consequences worth knowing: this is a *second* read-side resolution in the tree, and it deliberately uses the lenient `get_class` (no `StuffContent` bound, `None` rather than a raise) because the schema is optional decoration on a graph-registry entry.

**`--save-csv` resolves through `ConceptLibrary.make_empty()`, deliberately.** `PipelexMTHDSProtocol.execute` tears the run library down on its way out, so every post-run step in `_execute_run` has no current library — migrating this site to `get_concept_library()` turned `tests/e2e/pipelex/cli/test_csv_run.py` red with `RuntimeError: No current library set`. The old code never noticed because it read the process-global registry, which is never unregistered at teardown. An empty library reads that same registry while keeping the single typed "name → `StuffContent` subclass, or `ConceptStructureClassNotFoundError`" implementation. The lifecycle smell underneath is real and out of scope — recorded in `wip/inputs/unresolvable-structure-class-escapes-the-validate-sweep.md`.

**The scoping half is not done, and the branch no longer claims it is.** `ConceptLibrary.get_structure_class` calls `get_class_registry()`, which selects a registry from the current async context rather than from `self` — a `ConceptLibrary` holds no registry (the per-library `ClassRegistry` lives on `Library`). Codex flagged this as a P1 on the PR; it is a real mechanism, but the divergence it describes cannot occur: `get_concept_library()` and `_resolve_scoped_class_registry()` are two reads of the same `_library_id` ContextVar, and the one place that installs a per-library registry (`runtime_bridge/primitives/rehydration.py`) sets it and the ContextVar on the same library in adjacent statements. The proposed fix — carry a registry on the provider — would also break the two sites that deliberately depend on the ambient read (`--save-csv` post-teardown, and every boot-free test using `make_empty()`). Declined; the trip-wires that would make it real, the shape of the fix, and four sibling tradeoffs the finalize review surfaced — including that the new `StuffContent` bound tightened the *compatibility verdict* path as well as `get_structure_class` — are in `wip/inputs/provider-scoped-class-resolution.md`. What the review *did* correctly catch is that two new docstrings and the PR body overstated the property — those were corrected.

**Two `except` arms were removed rather than migrated, and two more were deliberately not added.** `resolve_input_kind` caught `ConceptValueError` and fell back to `InputKind.DYNAMIC`; `pipe_parallel` (combine) and `pipe_search` (structured output) call `get_structure_class()` unguarded on run paths where their *validation* siblings convert to `PipeValidationError`. All four concern the same question, and the answer is the same: `ConceptFactory` refuses to build a concept whose declared structure class does not resolve (`concept_factory.py` raises `ConceptFactoryError` on a bad `structure = "..."`, and the basic-blueprint path *generates* the class), and every `Concept(...)` construction in `pipelex/` source lives inside that factory. So the state is unreachable, keeping the fallback would restore exactly the silent degradation defect 2 removes, and adding two more guards would be guarding an impossible scenario. The asymmetry with the guarded validation siblings is intentional and explained in place: the `/validate` sweep needs per-pipe granularity or one bad pipe aborts the whole bundle, and a run has no sweep. Full reasoning, including what would have to change for this to become reachable, is in the wip note above.

## Deliberate non-goals

- **The materialization write side stays ambient.** `concept_factory` registering generated classes and `structure_generation/generator.py` looking up base classes are library-load-time concerns and genuinely the registry's business. Making libraries own their class registry explicitly is a separate, larger track.
- **No `StaticConceptProvider`** — build one when something needs it, not for symmetry.
- **No operator parameterization.** The interpreter-layer `get_concept_library()` calls introduced here are the sanctioned idiom for that layer today.
- **No wire-format change.** `structure_class_name` stays a plain `str` protocol field; nothing serialized changes shape, and no `mthds` schema edit is needed.

## Verification

`make agent-check` green (ruff, plxt, pyright, mypy, keyword-only, hub-layering). Full `make agent-test` green. Cross-repo usage of the four removed member names is **zero in code** (enumerated the workspace directory rather than a hardcoded list). Two live *documents* in other repos cite them and will want a follow-up when their tracks resume — tracked at workspace level; no code in either repo is affected. The transport boundary's `ALLOWED_SURFACE` names none of the touched symbols and no module moved, so no spec/conformance edit is due.

One registry hygiene note: `is_valid_structure_class` was demoted to keyword-only when it moved, so its now-dead entry was deleted from `subject_grants.toml` — the guard hard-fails on a stale grant, which is how it surfaced.
