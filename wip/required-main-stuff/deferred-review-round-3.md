# Deferred items — review round 3 (`/review` on PR #1014, pre-merge)

Independent context-free review (own critical pass + testing, maintainability, and adversarial sub-agents) on the full `dev..HEAD` diff. It converged on **one genuine latent defect** (F1), one verified robustness gap (F2), and cleanup items. The one test gap deemed worth closing in-PR (`DirectOrchestrator.start()` raise-path) was applied — see `tests/unit/pipelex/runtime_bridge/test_direct_orchestrator.py`. Everything below was **deliberately deferred** to keep the merge-ready PR frozen, since none is reachable in production today.

## F1 — Nested `CompositeContent` transport round-trip is asymmetric (latent silent corruption)

**Where:** encode `pipelex/core/memory/working_memory.py` (`_encode_composite_for_transport` / `_encode_content_with_class_markers`) vs decode `pipelex/runtime_bridge/primitives/hydration.py` (`_hydrate_composite_component` → `_hydrate_list_item`).

**What:** Encode recurses into a component that is itself a `CompositeContent` (stamping `__pipelex_class__="CompositeContent"`). Decode does **not** recurse: `_hydrate_list_item` resolves the `CompositeContent` class and calls `model_validate(clean_item)` without re-hydrating the inner components. Because `CompositeContent` is `extra="allow"`, the still-encoded inner components are stored verbatim — as raw `dict`s that **retain the pipelex-private `__pipelex_class__` / `__pipelex_module__` marker keys**.

**Failure scenario:** a nested `PipeParallel` (a branch whose own output is `Composite`), or a `CompositeContent` carried as a `ListContent` item, crosses the Temporal `dump_for_transport` → `hydrate_working_memory` boundary. The inner composite's components decay to `dict` (typed `.content_as(...)` / field access breaks) **and** `smart_dump()` / `rendered_markdown()` of that inner composite leaks the private marker keys into user/LLM-visible output. Silent — no exception at hydrate time. Confirmed by reproduction in the adversarial pass; the flat (depth-1) and `ListContent`-of-scalars cases are correct and tested — only the *nested composite* case is affected.

**Why deferred:** the Temporal/cross-process transport path has never shipped to production (see workspace memory `project_temporal_not_shipped`), and nested-parallel composition is an edge case. The corrupting code does ship in this PR, so this must be fixed **before the hosted-Temporal rollout**, not left indefinitely.

**Fix (small, localized):** in `_hydrate_list_item`, when the resolved class is a `CompositeContent` subclass, rebuild its components via `_hydrate_composite_component` before `model_validate` (mutual recursion; terminates on finite nesting). Add a nested round-trip test to `tests/unit/pipelex/core/stuffs/test_composite_content.py`: a composite whose component is a composite, asserting the inner component entries hydrate to typed `StuffContent` and carry no `__pipelex_*` keys.

## F2 — `ConceptValueError` (a bare `ValueError`) escapes the validate sweep

**Where:** `pipelex/pipe_controllers/parallel/pipe_parallel.py:153,223` call `concept.get_structure_class()`, which raises `ConceptValueError` (`pipelex/core/concepts/exceptions.py` — subclasses `ValueError`, **not** `PipelexError`; its sibling `ConceptError` does subclass `PipelexError`) when a structure class is not registered.

**What:** the validate sweep's step-1 wiring pass (`pipelex/pipeline/bundle_validator.py` `validate_with_libraries()`) catches only `PipeNotFoundError`; the per-pipe step-3 catch is `(PipelexError, ValidationError, FactoryException)`. A `ConceptValueError` matches neither, so it escapes `validate_pipes` and aborts validation of the **whole bundle** with an unhandled error instead of being reported as that one pipe's FAILURE. `PipeSequence`'s equivalent path avoids `get_structure_class()` (it uses `is_compatible`), so this exposure is net-new to `PipeParallel`.

**Why deferred:** low reachability — a loaded pipe's own output concept normally has its structure class registered. The failure mode (unhandled sweep abort vs clean per-pipe error) is poor DX but not a data-integrity issue.

**Fix (cheap):** catch `ConceptValueError` in `validate_output_with_library` and re-raise as `PipeValidationError` (or widen the sweep's step-1 catch).

## M1 — `rendered_html` table wrapper still duplicated

**Where:** `pipelex/core/stuffs/composite_content.py` (`rendered_html`) + `pipelex/core/stuffs/structured_content.py` (`rendered_html`).

**What:** the PR extracted per-value rendering into `render_value_html` (good), but the *table-of-named-values* wrapper and the verbatim empty-table literal (`<table><tr><td><em>empty</em></td></tr></table>`) are still copy-pasted in both classes — the same drift the extraction targeted, one level up.

**Fix:** add a shared `render_named_values_table(pairs)` helper in `html_rendering.py`; `StructuredContent` passes its non-`None` fields, `CompositeContent` passes all components. Pure refactor, no behavior change.

## Minor / noted (no action)

- **`combined_output_concept` graph execution-data key name** (`pipe_parallel.py`): now always `self.output.concept.concept_ref`. The misleading-name observation is correct, but the key is **deliberately kept** for `mthds-ui` compatibility — rename is already tracked as a Phase 3 cross-repo item (design open-question #2). Renaming before `mthds-ui`'s coordinated update would break it. Do not rename in-repo.
- **Unguarded `get_required_pipe` in `_validate_branch_output_types`** (`pipe_parallel.py`): asymmetric with `PipeSequence`'s cross-package-guarded form, but benign in the sweep (which anticipates unguarded sub-pipe resolution and catches `PipeNotFoundError`; `needed_inputs` would raise first anyway). Consistency nit for a future refactor.
- **`PipelexRunResultExecute.from_pipe_output`** (`pipeline/pipeline_response.py`): accepts non-`COMPLETED` states but unconditionally calls the now-raising `resolve_main_stuff_root_key`. Latent only — the sole caller passes `state=COMPLETED` on the success path. A future caller routing a failed `PipeOutput` here would have the real failure masked by a secondary `PipeJobError`. Tighten by asserting completion or dropping the `state` param if a caller ever needs the failed path.
- **Duplicate branch-result-name detection** stays a runtime guard (`validate_output_with_library` builds `result_names` as a set, silently collapsing duplicates; the runtime duplicate guard with its stale `# TODO` remains). Design tradeoff, not a bug — the runtime guard still catches it.
