# Concept purity — evict the ambient class-registry reads from the core concept model

**Execution target:** this worktree (`_concept`), on branch `refactor/Concept-purity`, already cut from `dev` at `ed7435a7c` — the exact commit the inventory below was measured on, so every `file:line` locator is exact. Treat this worktree as the repo root. This document is the working tracker: update the checkpoint sections as phases complete.

**Lineage:** this continues the hub-split / layer-placement line of work (#1062, #1064, #1070, #1071) — same doctrine, applied to the last ambient lookup left inside the core concept model.

## Verdict (why this is worth doing)

`Concept` (`pipelex/core/concepts/concept.py`) is a subclass of the MTHDS-protocol wire model `ConceptAbstract` (`mthds/protocol/concept.py`: `code`, `domain_code`, `description`, `structure_class_name: str`, `refines`). It is pure serializable data — except that four of its methods answer behavioral questions by reaching into the process-global class registry via `get_class_registry()` (`system/registries/class_registry_access.py`), which that module's own docstring identifies as the reason the accessor has to sit below both hubs. Three independent reasons to fix this now:

1. **It fixes two live bugs and one hazard, today.**
   - *Resolver bypass:* five call sites call `Concept.are_concept_compatible` directly instead of `ConceptLibrary.is_compatible` (`pipe_llm.py:246,334`, `template_image_analyzer.py:218,227`, `template_document_analyzer.py:151`), so `concept_resolver=None` and cross-package `refines` aliases silently fail to resolve there — wrong compatibility verdicts at authoring time and on the PipeLLM text-vs-object run branch. Every other compat check in the tree goes through the wrapper.
   - *Silent wrong answer:* `are_concept_compatible` returns `False` — not an error — when either structure class is absent from the registry (`concept.py:133-137`). "Unknown" and "incompatible" are different answers; conflating them is a latent wrong-verdict bug for any concept whose class isn't in the ambient registry (executed proof in the review).
   - *Ambient scoping hazard:* `get_class_registry()` resolves through per-library scoping (`class_registry_scoping`), so the same two `Concept` values can answer compatibility differently depending on which async context asks. Compatibility should be a function of the library you ask, explicitly.
2. **It completes the hub split's own doctrine.** `docs/contribute/hub-layering.md` §"Injected providers, not ambient lookups" created `ConceptProviderAbstract` precisely so `core/` states its dependencies as parameters. The split moved concept *resolution* to the provider but left class *resolution* ambient inside the core model — the provider's `is_compatible` bottoms out in a global-registry read hidden in `Concept`. This finishes that move and removes the main justification for `class_registry_access` sitting below the hubs.
3. **Brand/layer correctness + testability.** A standard-owned wire model should not be coupled to a Pipelex process-global. After the refactor the compatibility matrix is testable with plain classes and no boot, and the declaration tier with no registry at all.

**Honest scoping:** this removes the wrongness class at its source and makes explicit-class passing the only API shape, so "don't call registry-backed `Concept` methods" stops being discipline and becomes the path of least resistance. Blast radius is measured and small (see inventory below); cross-repo usage of the four methods is **zero** (grep across the workspace on 2026-07-29 — re-confirm at execution). No wire-format change anywhere: `structure_class_name` stays a `str` field; nothing serialized changes shape.

## Target end state

- `pipelex/core/concepts/concept.py` has **no** import of `class_registry_access` — every remaining method is a pure function of the model's fields (plus the already-injected `concept_resolver`).
- Class-based compatibility is a pure function over resolved classes; the composition (declaration tier → resolve classes → class tier) lives in `ConceptLibrary.is_compatible`, the one place that legitimately owns resolution.
- `ConceptProviderAbstract` grows `get_structure_class(concept) -> type[StuffContent]`; all class resolution goes through a provider (core layer) or the concept library (interpreter layer).
- Unresolvable structure classes fail **loud** with a dedicated error, never a silent `False`.
- The write side is untouched and stays put: `concept_factory.py` registering generated classes and `structure_generation/generator.py` looking up base classes are materialization-time concerns and remain the only sanctioned `core/concepts/` users of `class_registry_access` — pinned by a test.

## Measured inventory (as of dev `ed7435a7c` — this worktree's HEAD)

The four registry-reaching members of `Concept` and every source call site:

- `are_concept_compatible` (`concept.py:86`): `concept_library.py:99` (the wrapper), plus the five bypass sites listed above.
- `get_structure_class()` (`concept.py:166`, already raises `ConceptValueError` when missing): internal `concept.py:213,232` (render); external `input_shaper.py:245`, `stuff_factory.py:237`, `pipe_abstract.py:178`, `pipe_parallel.py:168,386,459`, `pipe_search.py:143`, `builder/runner_code.py:118`, `cli/commands/run/_run_core.py:346`.
- `is_valid_structure_class` (`concept.py:159`): only `concept_factory.py:305,371,373` — authoring/load-time only.
- `search_for_nested_image_fields_in_structure_class` (`concept.py:178`): only `template_image_analyzer.py:234,243`.

Render cascade: `Concept.render_concept_representation` ← `StuffSpec.render_stuff_spec` (`stuff_spec.py:51`) ← `pipe_io_contracts.py:107`, `input_shaper.py:615` (`_render_expected_shape`, D4 error hints), `input_stuff_specs.py:187` (`build_inputs_template`), `output_renderer.py:53,92,187,228,272`; plus direct caller `builder/runner_code.py:229`.

Pre-existing bugs to fix while there (flag-and-fix rule): `pipe_parallel.py:459` and `pipe_search.py:143` call `get_structure_class()` unguarded on run paths and can leak a raw `ConceptValueError` (their validation siblings at `pipe_parallel.py:168,386` convert properly).

Tests: main compat matrix at `tests/unit/pipelex/core/concepts/test_concept.py:274-413`; `concept_resolver` covered only by `test_concept_cross_package_refines.py`; provider-injection pinned by `tests/unit/pipelex/core/memory/input_shaper/test_provider_injection.py`; `--save-csv` guard mocks at `tests/unit/pipelex/cli/test_run_core_execution.py:413,432`; image-field paths at `test_concept_find_image_field_paths.py`. `is_valid_structure_class` has no direct coverage.

---

## Phase 0 — setup + red tests ✅

- [x] Verify the venv is synced to this tree (`make install` if it predates the branch), and that `make tb` boots clean before any edits.
- [x] Re-run the cross-repo grep for the four method names across the workspace repos; confirm still zero external usage (enumerate the workspace dir, don't hardcode the repo list). **Result: zero.** The only workspace hits outside this repo are historical prose under the workspace-root `docs/history/` and `wip/`.
- [x] **Red test — resolver bypass:** `tests/unit/pipelex/pipe_operators/pipe_llm/test_template_image_analyzer_cross_package.py`, driven through the *public* `analyze_template_for_images` rather than the private resolver, so it pins observable behavior. Failed red with `0 == 1` (no image reference produced).
- [x] **Red test — loud failure:** `tests/unit/pipelex/libraries/test_concept_library_compatibility.py`.
- [x] **Red test — pure declaration tier:** `tests/unit/pipelex/core/concepts/test_concept_declaration_compatibility.py`.

## Phase 1 — decompose compatibility ✅

- [x] Add `are_structure_classes_compatible(*, class_1: type[Any], class_2: type[Any], strict: bool) -> bool` in `pipelex/tools/typing/class_utils.py` next to `are_classes_equivalent`/`has_compatible_field`: equivalence → `True`; `strict` → `False`; else subclass check → field compat. Pure — takes classes, never names.
- [x] Reshape `Concept.are_concept_compatible` into `Concept.are_compatible_by_declaration(*, concept_1, concept_2, concept_resolver=None) -> bool` — the current string tier only. `True` means established by declarations; `False` means *not established at this tier* (docstring states the asymmetry). Zero registry access.
- [x] Add `ConceptStructureClassNotFoundError` to `pipelex/core/concepts/exceptions.py`, subclass of `ConceptValueError`. **`make gei`/`make gep` were no-ops** — both generators enumerate `PipelexError` subclasses, and `ConceptValueError` descends from `ValueError`, so this family is outside their scope. Nothing to regenerate.
- [x] Recompose `ConceptLibrary.is_compatible`: declaration tier first; if inconclusive, resolve both classes (loud) and delegate to `are_structure_classes_compatible`.
- [x] Route the five bypass sites through the library. Direction and strict semantics matched the inventory at all five; no surprises.
- [x] Delete the old `are_concept_compatible` and migrate the tests.

**CHECKPOINT 1** ✅ — compatibility consolidated. `make agent-check` green (incl. pyright/mypy/kw-only/hub-layering), full `make agent-test` green.

### Surprises worth carrying forward

- **`native.Anything` declares no structure class at all.** `NativeConceptCode.ANYTHING.structure_class` is `None` by design (it is the untyped vehicle), while `structure_class_name` still derives `"AnythingContent"` mechanically — a name no registry ever holds. The silent-`False` was masking that: `is_compatible(Anything, Text)` answered `False` for the *wrong reason*. Fixed properly rather than papered over: `NativeConceptCode.is_structureless_concept` + `Concept.declares_a_structure_class` make "this concept has no structure" a declared property, and `ConceptLibrary.is_compatible` returns `False` for it before reaching the class tier. Verdicts are unchanged; only the reasoning is now correct. Pinned by `test_the_structureless_native_concept_is_answered_not_raised`.
- **Test consolidation.** `test_concept_cross_package_refines.py` was deleted, not rewritten: every one of its rows is covered (and better organised) by the new declaration-tier module. The end-to-end matrix that lived in `test_concept.py` moved to the library test module, where it now belongs.
- `ConceptProviderAbstract.get_structure_class` landed in Phase 1 rather than Phase 2, because `is_compatible`'s new composition needs it. Phase 2 only migrates call sites onto it.

## Phase 2 — class access exits `Concept`

- [ ] Add `get_structure_class(concept: Concept) -> type[StuffContent]` to `ConceptProviderAbstract`; implement in `ConceptLibrary` via the active registry, enforcing the `StuffContent` subclass bound (`get_required_subclass` semantics — a deliberate tightening over today's uncheck-and-return; raises `ConceptStructureClassNotFoundError`). ⚠ Subject-grant mechanics: if `concept` stays positional, record the grant (`make sgr FUNC=… RATIONALE=…`) **before** running `make agent-check`, or the auto-fixer will silently keyword-only it.
- [ ] Migrate the external `get_structure_class()` call sites to the provider/library: `input_shaper.py:245` and `stuff_factory.py:237` (provider already in scope); `pipe_abstract.py:178`, `pipe_parallel.py:168,386,459`, `pipe_search.py:143`, `builder/runner_code.py:118`, `_run_core.py:346` (interpreter/CLI layer — `get_concept_library()`).
- [ ] While touching them, fix the two unguarded run-path sites: `pipe_parallel.py:459` and `pipe_search.py:143` convert the error the way their validation siblings do instead of leaking it raw.
- [ ] Render chain: `Concept.render_concept_representation` and `_render_schema_representation` take `structure_class: type[StuffContent]` as a parameter (they keep using `self.concept_ref` for labeling). `StuffSpec.render_stuff_spec` gains a `concept_provider` parameter, resolves once, passes the class down. Thread the provider through the callers: `output_renderer.py` (×5) and `pipe_io_contracts.py` (interpreter layer), `input_stuff_specs.build_inputs_template` (parameter, callers are interpreter-side), `input_shaper._render_expected_shape` → `_wrong_kind` chain (callers hold the provider), `builder/runner_code.py:229`.
- [ ] Move `is_valid_structure_class` into `concept_factory.py` as a private module-level helper (its only three callers live there). Delete it from `Concept`.
- [ ] Delete `search_for_nested_image_fields_in_structure_class`; at `template_image_analyzer.py:234,243` compose `get_concept_library().get_structure_class(concept)` + the existing free function `search_for_nested_image_fields(content_class=…)`. Keep the current raise-on-non-StuffContent behavior (now uniform via the provider method).
- [ ] Migrate/adjust the touched tests (`test_concept_find_image_field_paths.py`, `test_run_core_execution.py` mocks, input-shaper tests).

**CHECKPOINT 2** — class access consolidated; `concept.py` should have no remaining `get_class_registry` call sites. Run the full targeted suite; `make cleanderived` if pytest collection is confused by moved tests. Update this doc with status + decisions.

## Phase 3 — purity lock + docs

- [ ] Drop the `class_registry_access` import from `concept.py`. Add a golden-set boundary test (style precedent: `tests/unit/pipelex/cogt/test_cogt_dependency_boundaries.py`) pinning that within `pipelex/core/concepts/`, only `concept_factory.py` and `structure_generation/generator.py` import `class_registry_access` — a new edge is a red diff a reviewer reads.
- [ ] Update the `class_registry_access.py` module docstring: its "concept.py needs me from inside runtime_hub's closure" justification is gone; the remaining core users are the materialization write side.
- [ ] Update `docs/contribute/hub-layering.md` §"Injected providers, not ambient lookups" to cover class resolution (the provider now answers "what is this concept's structure class", not just "resolve this ref"). Grep `docs/` for the four old method names and fix stale mentions.
- [ ] Changelog under `[Unreleased]`: breaking — `Concept.are_concept_compatible` replaced by `Concept.are_compatible_by_declaration` + `ConceptLibrary.is_compatible` composition; `Concept.get_structure_class` / `is_valid_structure_class` / `search_for_nested_image_fields_in_structure_class` removed (provider/factory own resolution); fixed — cross-package `refines` resolution at the former bypass sites, silent-`False` on unregistered structure classes now raises, unguarded run-path `ConceptValueError` leaks in `PipeParallel`/`PipeSearch`.

## Phase 4 — gates + PR

- [ ] `make agent-check` (grants recorded first), `make agent-test`, `make tb` if any config was touched (should be none).
- [ ] Re-confirm zero cross-repo usage of the removed names; `pipelex-transport`'s `ALLOWED_SURFACE` is unaffected (no module moved) — one-line sanity check, no spec edit expected.
- [ ] PR to `dev`: completes the hub split's provider doctrine for class resolution, fixes the resolver-bypass and silent-False bugs, purifies the protocol-owned wire model.

## Non-goals (deliberate)

- The factory/generator **write side** stays ambient — registering generated classes at materialization is the library-load pipeline's business; making libraries own their class registry explicitly is a separate, larger track.
- No `StaticConceptProvider` — build it when something needs it (per the review's F3 note), not for symmetry.
- No operator parameterization (F2 territory): the interpreter-layer `get_concept_library()` calls introduced here are the sanctioned idiom for that layer today.
- No `mthds` schema change: `structure_class_name` stays a plain `str` protocol field.

## Risks / watch items

- The silent-`False` → raise change can surface in tests or exotic paths that constructed `Concept`s outside a loaded library; every such surfacing is a finding, not a regression — triage each deliberately.
- `core/` is high-churn and several worktrees are in flight; the edits are mostly mechanical but land this in a quiet merge window to limit conflicts.
- The auto-fixer keyword-onlys ungranted positional subjects silently — record grants before checks (bitten before; see `subject_grants.toml` flow).
