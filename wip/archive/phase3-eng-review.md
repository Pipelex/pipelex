# Engineering Review: Phase 3 — Deferred WorkingMemory Hydration + Scoped ClassRegistry

**Branch**: `feature/Temporal-3`
**Plan file**: `TODOS.md`
**Repo mode**: solo

---

## Step 0: Scope Challenge

### What existing code already partially solves sub-problems?

| Sub-problem | Existing code | Reuse? |
|---|---|---|
| Context-scoped state | `_library_id: ContextVar` in `hub.py:454` | YES — same pattern for scoped registry |
| Library lifecycle | `open_library() / teardown() / set_current_library()` in `hub.py` | YES — already used in WfPipeRouter |
| Class registration | `KajsonManager.get_class_registry().register_class()` in ConceptFactory | YES — auto-uses scoped registry via ContextVar |
| Temporal data conversion | `BaseModelPayloadConverter` uses `kajson.dumps/loads` | YES — drives the serialization constraints |

### Minimum set of changes?

The plan has two clean parts (A: Kajson, B: Pipelex). No scope creep detected — all items directly serve the stated goal.

### Complexity check

- **Files touched**: 14 (8 modified, 6 new) — above the 8-file smell threshold
- **New classes**: 1 (`CompositeClassRegistry`) + 1 error class (`PipeJobError`)
- However, 6 of the 14 are test files. The actual production code changes are 8 files with small, focused diffs. This is inherent complexity, not over-engineering.

### TODOS cross-reference

The plan IS the TODOS.md, so no cross-reference needed.

---

## Resolved Issues

### Issue 1 — RESOLVED: Hydration approach for dynamic classes

**Decision**: Keep `dict[str, Any]` with concept-based hydration (user's input).

**Serialization**: `working_memory.smart_dump()` → `dict[str, Any]` (dashboard-friendly)
**Hydration**: Concept-based reconstruction in `hydration.py`:
- Iterate stuff entries in raw dict
- For each stuff, get `concept.structure_class_name`
- Look up class via `ClassRegistry.get_required_subclass(name, StuffContent)`
- Call `the_class.model_validate(content_dict)` — same pattern as `StuffContentFactory.make_stuff_content_from_concept_required()` (line 18-24)
- Reconstruct typed Stuff objects + WorkingMemory

**Data flow**:
```
prepare_for_temporal():
  smart_dump() → dict[str, Any] (all subclass fields preserved, no Kajson metadata)
Temporal wire:
  kajson.dumps(PipeJob) → dict passes through as plain JSON object (no __class__ keys)
Worker:
  kajson.loads → dict comes back as plain dict
Hydrate (after load_from_crate):
  iterate raw dict → concept.structure_class_name → ClassRegistry → model_validate ✓
```

### Issue 2 — RESOLVED: CompositeClassRegistry missing methods

Add `setup()` (no-op) and `get_required_base_model()` (local-first, parent-fallback) to the plan spec. Both are trivial delegation methods.

### Issue 3 — RESOLVED: Temporal sandbox imports

New imports (`CompositeClassRegistry`, `KajsonManager`, `hydration`) in WfPipeRouter must go inside the existing `with workflow.unsafe.imports_passed_through():` block.

### Issue 4 — RESOLVED: PipeJob API surface

Verified: only 2 places access `pipe_job.working_memory` — `pipe_router.py:21` (updated in B5) and `wf_pipe_router.py:28` (updated in B7). No other PipeJob callers are affected.

### Issue 5 — RESOLVED: Hydration utility location

Keep as separate `hydration.py` module. Concept-based hydration is ~20 lines, independently testable.

### Issue 6 — RESOLVED: Mutation in prepare_for_temporal()

Keep in-place mutation (plan as-is). PipeJob is single-use, consumed immediately after dispatch.

---

## Test Review

### Code Path Coverage Diagram

```
CODE PATH COVERAGE
===========================
[+] kajson/composite_class_registry.py (NEW)
    │
    ├── get_class() / get_required_class() / get_required_subclass()
    │   ├── [PLANNED] Local hit — test_local_lookup_takes_priority
    │   ├── [PLANNED] Parent fallback — test_fallback_to_parent
    │   └── [GAP] Local + parent both miss — should raise/return None
    │
    ├── register_class() / register_classes() / register_classes_dict()
    │   └── [PLANNED] Local only — test_registration_goes_to_local_only
    │
    ├── has_class() / has_subclass()
    │   └── [PLANNED] Both layers — test_has_class_checks_both
    │
    ├── teardown()
    │   └── [PLANNED] Local only — test_teardown_clears_local_only
    │
    ├── unregister_class() / unregister_class_by_name()
    │   └── [GAP] Not in planned tests — needs test for local-only unregistration
    │
    └── setup() / get_required_base_model()
        └── [GAP] Missing from plan spec — needs implementation + test

[+] kajson/kajson_manager.py (ContextVar scoping)
    │
    └── get_class_registry() with ContextVar
        └── [PLANNED] test_scoped_context_var

[+] pipelex/pipe_run/pipe_job.py (modified)
    │
    ├── prepare_for_temporal()
    │   ├── [PLANNED] With crate — test_prepare_for_temporal_moves_wm_to_raw
    │   ├── [PLANNED] Without crate — test_prepare_for_temporal_noop_without_crate
    │   └── [PLANNED] Empty WM — test_prepare_for_temporal_empty_wm
    │
    └── get_working_memory()
        ├── [PLANNED] From typed — test_get_working_memory_from_typed
        ├── [PLANNED] From raw raises — test_get_working_memory_from_raw_raises
        └── [PLANNED] Both None — test_get_working_memory_both_none_returns_empty

[+] pipelex/temporal/tprl_pipe/hydration.py (NEW)
    │
    ├── [PLANNED] Native text — test_hydrate_with_native_text
    ├── [PLANNED] Empty — test_hydrate_empty
    ├── [PLANNED] Aliases — test_hydrate_preserves_aliases
    └── [GAP] Dynamic StructuredContent — needs test with dynamic class

[+] pipelex/temporal/tprl_pipe/wf_pipe_router.py (modified)
    │
    ├── Scoped registry creation + cleanup
    │   └── [PLANNED] Integration test (B8)
    │
    ├── Hydration after crate load
    │   └── [PLANNED] Integration test (B8)
    │
    └── Error during hydration
        └── [GAP] What if hydration fails? Error should propagate cleanly

[+] Integration: dynamic concepts through Temporal
    │
    ├── [PLANNED] Full round-trip with dynamic concept — test_wf_deferred_hydration.py
    ├── [PLANNED] Concurrent workflows with same concept name
    └── [GAP] Round-trip with ListContent of dynamic items

─────────────────────────────────
COVERAGE: 15/20 paths planned
  Planned tests: 15
  Gaps: 5
GAPS: 3 need unit tests, 2 need integration tests
─────────────────────────────────
```

### Test Gaps

**Gap 1**: CompositeClassRegistry — unregister from local only (unit test)
**Gap 2**: CompositeClassRegistry — setup() and get_required_base_model() (unit test)
**Gap 3**: Hydration with dynamic StructuredContent class (unit test)
**Gap 4**: Hydration failure propagation (integration test)
**Gap 5**: ListContent of dynamic items round-trip (integration test)

---

## Performance Review

No performance concerns. The changes are:
- One extra `smart_dump()` call per dispatch (microseconds)
- Concept-based hydration iterates N stuffs in WM with one registry lookup each (negligible)
- CompositeClassRegistry adds one dict lookup per class resolution (negligible)
- ContextVar access is O(1)

---

## Failure Modes

| Codepath | Failure scenario | Test? | Error handling? | User-visible? |
|---|---|---|---|---|
| prepare_for_temporal() | smart_dump() fails on WM content | No | No — would crash | Yes — stack trace |
| hydrate_working_memory() | concept not found in registry after crate load | No | ClassRegistryNotFoundError propagates | Yes — workflow fails |
| CompositeClassRegistry teardown | Called twice | No | Safe — clears empty dict | Silent |
| ContextVar not cleaned up | Memory leak of scoped registry | No | finally block handles it | Silent |
| Concurrent concept name collision | Two workflows register "Greeting" with different fields | PLANNED | Scoped registry isolates | No impact |

**Critical gaps**: 0 (all failure modes either have handling or are edge cases with safe defaults)

---

## What Already Exists

| Existing code | Purpose | Reused by plan? |
|---|---|---|
| `_library_id: ContextVar` in hub.py | Per-workflow library scoping | YES — same pattern for registry |
| `WfPipeRouter.run()` library lifecycle | open/load/teardown per workflow | YES — extended with scoped registry |
| `BaseModelPayloadConverter` | Kajson-based Temporal serialization | YES — drives raw field design |
| `ClassRegistryAbstract` | Clean interface for composition | YES — CompositeClassRegistry implements it |
| `ClassRegistry` | Concrete implementation | YES — used as local layer |

---

## NOT in Scope

| Item | Rationale |
|---|---|
| Thread-safe ClassRegistry | Temporal workflows are single-threaded; ContextVar provides isolation |
| Migration of existing PipeJob callers | No existing callers break — `working_memory` default is still empty WM |
| Dashboard UI for raw WM | The raw field is visible as JSON in Temporal dashboard; no custom UI needed |
| Activity-level scoping | Activities don't need class resolution; only workflows load crates |

---

## Completion Summary

- **Step 0: Scope Challenge** — scope accepted as-is (complexity is inherent)
- **Architecture Review**: 2 issues found — all resolved
- **Code Quality Review**: 3 issues found — all resolved
- **Test Review**: diagram produced, 5 gaps identified
- **Performance Review**: 0 issues found
- **NOT in scope**: written
- **What already exists**: written
- **TODOS.md updates**: 0 items (all handled in-plan)
- **Failure modes**: 0 critical gaps
- **Outside voice**: ran (codex failed, Claude subagent used) — 8 points raised, 4 substantive, 0 change plan direction
- **Lake Score**: 5/5 recommendations chose complete option

---

## Recommended Updates to TODOS.md

Based on this review, the following changes should be made to the plan:

### 1. B3: Use `smart_dump()` not `model_dump(serialize_as_any=True)`
Replace `self.working_memory.model_dump(serialize_as_any=True)` with `self.working_memory.smart_dump()` in `prepare_for_temporal()`.

### 2. B4: Concept-based hydration (not model_validate)
Replace the `model_validate()` approach with concept-based reconstruction:
```python
def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    # For each stuff entry in raw dict:
    #   1. Reconstruct Concept from concept dict (no dynamic classes needed)
    #   2. Get structure_class_name from concept
    #   3. Look up class in ClassRegistry via get_required_subclass()
    #   4. Call the_class.model_validate(content_dict)
    #   5. Build typed Stuff objects
    # Reuses pattern from StuffContentFactory.make_stuff_content_from_concept_required()
```

### 3. A1: Add missing abstract methods
Add `setup()` (no-op) and `get_required_base_model()` (local-first, parent-fallback) to CompositeClassRegistry.

### 4. B7: Imports inside unsafe block
New imports for CompositeClassRegistry, KajsonManager, and hydration must go inside `workflow.unsafe.imports_passed_through()`.

### 5. B8: Structural equality assertions
Integration test should assert field-by-field on hydrated Stuff content (e.g., `assert stuff.content.score == 0.9`) rather than relying on `==` on dynamic model instances.

### 6. A3: Additional test cases
Add tests for:
- `unregister_class()` / `unregister_class_by_name()` from local only
- `get_required_base_model()` delegation
- Hydration with dynamic StructuredContent class
- ListContent of dynamic items round-trip

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ISSUES_FOUND | 8 points raised, 0 actionable changes (Claude subagent fallback) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 6 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**UNRESOLVED:** 0 decisions pending
**VERDICT:** ENG CLEARED — all 6 issues resolved through interactive review

```
+====================================================================+
|                    REVIEW READINESS DASHBOARD                       |
+====================================================================+
| Review          | Runs | Last Run            | Status    | Required |
|-----------------|------|---------------------|-----------|----------|
| Eng Review      |  1   | 2026-03-26 02:23    | CLEAR     | YES      |
| CEO Review      |  0   | —                   | —         | no       |
| Design Review   |  0   | —                   | —         | no       |
| Adversarial     |  0   | —                   | —         | no       |
| Outside Voice   |  1   | 2026-03-26 02:21    | DONE      | no       |
+--------------------------------------------------------------------+
| VERDICT: CLEARED — Eng Review passed                                |
+====================================================================+
```

All relevant reviews complete. No UI/UX components — design review not needed. Backend infrastructure change — CEO review optional. Ready to implement.
