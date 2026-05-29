# Data-Class Best-Practices Refactor — Working Ledger (`refactor/Dataclasses`)

Give every data holder the right shape: `BaseModel` (or, after Phase 0, a pydantic dataclass) for anything on the Temporal wire; `NamedTuple` for small fixed immutable off-wire records replacing bare tuples; frozen `BaseModel` for immutable validated off-wire value objects; plain mutable `BaseModel` where the object is genuinely mutated in place. Eradicate every stdlib `@dataclass` (HARD RULE 1).

Phase 0 is the foundation: generalize the Temporal converter (and kajson, in `../kajson`) so pydantic dataclasses are wire-legal, relaxing the "must be BaseModel on the wire" constraint. It is purely additive — no current wire type is a pydantic dataclass, so no existing payload changes. Everything after Phase 0 is off-wire and chosen per-site.

This ledger supersedes the completed `feature/API-readiness-4` ledger (archived to `wip/error-handling/archive-todos-api-readiness-4.md` on 2026-05-29). The original free-form plan that seeded this ledger was at `wip/data-class-best-practices-plan.md` (now removed; this file replaces it).

---

## Cold-start reading order

A fresh session should read, in order:

1. **This file, top to bottom.** It is the single source of truth for what to do and what's done.
2. **The "Session log" at the bottom** — the most recent entry is the handoff note from the last session: what landed, decisions taken, open questions, and the exact next action.
3. **`pipelex/temporal/temporal_data_converter.py`** — the converter being generalized in Phase 0. Read `BaseModelPayloadConverter.to_payload` / `from_payload`.
4. **`../kajson/kajson/json_decoder.py`** (`_apply_decoder_strategies`, ~line 196) and **`json_encoder.py`** (`default`, ~line 107) — the kajson dispatch Phase 0 extends.
5. The per-item detail sections below carry the *why* for each conversion; trust them but re-confirm any path/line reference against the current tree before editing (the off-wire audit was originally taken against a sibling `refactor/Paths` worktree).

---

## How to use this ledger

- **Checkboxes** track progress. Flip `[ ]` → `[x]` the moment a task lands (with its verification green), and append a one-line result (what changed + where) right under it. Do not batch.
- **Checkpoints are HARD STOPS.** When you reach a `🛑 HARD STOP` marker you MUST end the session after completing the context-save protocol below — do not roll into the next phase in the same session. They sit at natural handoff points where a coherent unit has landed and context has grown enough to warrant a fresh start.
- **Context-save protocol** (run at every hard stop, before ending the session):
  1. Flip all completed checkboxes and write their one-line results.
  2. Append a new **Session log** entry (template at the bottom): date, what landed, decisions taken, open questions, current code state (clean? mid-edit?), and the single exact next action for the next session.
  3. Record any deviation from this plan inline in the relevant item, with the reason.
  4. Confirm the tree is in a clean, committed (or clearly-described) state — the next session must be able to cold-start with zero memory of this one.
- **Verification commands** (run as noted per phase; never skip on a hard stop):
  - `make agent-check` — after every code change.
  - `make tb` — after any change touching boot/config/import paths.
  - `.venv/bin/pytest tests/integration/pipelex/temporal/` — after any change in `pipelex/temporal/` or the converter/kajson.
  - `make agent-test` — full suite, at the final gate.

---

## Safety boundary — wire types must be BaseModel or pydantic dataclass

These types cross the Temporal wire directly or transitively. After Phase 0, each MUST be a `BaseModel` **or** a pydantic dataclass — the two forms `BaseModelPayloadConverter` routes through kajson with type preservation. A `NamedTuple`, stdlib dataclass, or arbitrary class here falls through to Temporal's stock JSON path and silently corrupts distributed execution or hard-fails deserialization.

**Every type on this list currently is, and should remain, a `BaseModel`.** They rely on machinery pydantic dataclasses don't provide as cleanly — discriminated unions, model validators, `model_dump`, the dynamic-class `__kajson_class_source__` mechanism. Phase 0 widens what is *legal* on the wire; it does NOT motivate converting anything already here. Do not convert these to pydantic dataclasses just because Phase 0 makes it possible.

- `PipeRunArg` (`pipelex/temporal/tprl_pipe/pipe_run_arg.py`) — direct argument of `WfPipeRun.run`. Already `BaseModel`.
- `PipeJob` (`pipelex/pipe_run/pipe_job.py`) — argument of `WfPipeRouter.run`; field of `PipeRunArg`.
- `PipeOutput` (`pipelex/core/pipes/pipe_output.py`) — return of both router workflows; field of `DeliveryActivityArg`.
- `DeliveryAssignment` (`pipelex/pipe_run/delivery_assignment.py`) — field of `PipeRunArg` and `DeliveryActivityArg`.
- `DeliveryActivityArg` (`pipelex/temporal/tprl_pipe/act_deliver.py`) — argument of `act_deliver`.
- `DeliveryStatus` (StrEnum, `pipelex/pipe_run/delivery_assignment.py`) — enclosed in `DeliveryActivityArg`; the StrEnum is fine, keep the enclosing type a `BaseModel`.
- `ErrorReport` (`pipelex/base_exceptions.py`) — field of `DeliveryActivityArg`.
- `AssembleGraphArg` (`pipelex/temporal/tprl_pipe/act_assemble_graph.py`) — argument of `act_assemble_graph`.
- `GraphSpec` (`pipelex/graph/graphspec.py`) — return of `act_assemble_graph`; field of `PipeOutput`.
- `PipelineRef` (`pipelex/graph/graphspec.py`) — embedded in the returned `GraphSpec`.
- `FlushTraceEventsArg` (`pipelex/temporal/tprl_pipe/act_flush_trace_events.py`) — argument of `act_flush_trace_events`.
- `JobMetadata` (`pipelex/pipeline/job_metadata.py`) — field of `PipeJob`.
- `GraphContext` (confirm path: `grep -rn "class GraphContext" pipelex/`) — field of `JobMetadata`, transitively on `PipeJob`.
- `WorkingMemory` (`pipelex/core/memory/working_memory.py`) — field of `PipeJob` and `PipeOutput`.
- `PipeRunParams` (`pipelex/core/pipes/pipe_run_params.py`) — field of `PipeJob`.
- `PipeAbstract` + all concrete pipe subclasses (`pipelex/core/pipes/pipe_abstract.py`; confirm) — the `pipe` field of `PipeJob`.
- `LibraryCrate` (confirm path: `grep -rn "class LibraryCrate" pipelex/`) — field of `PipeJob`.
- `Stuff` (`pipelex/core/stuffs/stuff.py`) — contained in `WorkingMemory`.
- `StuffContent` + the entire discriminated-union hierarchy (`pipelex/core/stuffs/stuff_content.py`): `TextContent`, `ImageContent`, `PdfContent`, `ListContent`, `StructuredContent`, `HtmlContent`, `NumberContent`, etc.
- `ImageContent` — return element of content-gen activities (`list[ImageContent]`).
- `PageContent` (confirm exact file) — return element of a content-gen activity (`list[PageContent]`).
- Page-view content payload(s) — returned by the render-page-views activity, embedded in `PageContent.page_view`. Confirm exact class name(s) by reading the activity return annotation and the `PageContent.page_view` field BEFORE touching anything nearby; highest-risk list-element serialization spot.
- `TraceEvent` + subtypes (`pipelex/tracing/...`) — element type of `FlushTraceEventsArg.events`. Confirm via the `events` annotation and `BufferingEventLog.drain` return type.

---

## Pre-flight — freeze the boundary (do before any edit)

- [ ] Re-confirm the wire layer is clean: `grep -rn "@dataclass\|NamedTuple" pipelex/temporal/` returns nothing.
- [ ] Resolve every "confirm path" entry in the safety boundary above (`GraphContext`, `LibraryCrate`, `PipeAbstract`, `PageContent`, page-view payload, `TraceEvent`) and pin the paths.

---

## Phase 0 — Generalize the converter (+ kajson) to accept pydantic dataclasses

Goal: stop the converter from being the sole arbiter of domain-model shape. Today `BaseModelPayloadConverter` routes only `BaseModel` / `Optional[BaseModel]` / `list[BaseModel]` through kajson; everything else falls through to Temporal's stock JSON. Phase 0 widens that to pydantic dataclasses (and `Optional` / `list` of them). Scope is pydantic dataclasses ONLY — `NamedTuple` stays out (kajson flattens it to a bare JSON array, losing field names + type), stdlib dataclasses stay out (HARD RULE 1 eradicates them), arbitrary classes stay out (unsafe `__dict__`-replace path).

### Layer 1 — kajson (`../kajson`, editable via this worktree's `uv.lock`)

kajson v0.5.0 has no dataclass support and no dataclass tests. A pydantic dataclass currently only survives via the untested generic catch-all: encode via `__dict__` (`json_encoder.py` ~160), decode via `the_class(**the_dict)` (`json_decoder.py` ~293). The decode path is fragile — if validation raises there, the next line swallows it (`except Exception: pass`) and falls through to the unsafe `obj.__dict__ = the_dict` path, then to returning a raw dict. Silent corruption instead of a loud error.

- [ ] **0.1** Add an explicit pydantic-dataclass branch in `_apply_decoder_strategies` (after the `Enum` / `BaseModel` branches, before the generic constructor), using `pydantic.dataclasses.is_pydantic_dataclass`. Reconstruct via the dataclass' pydantic validator (validates), and on `ValidationError` raise `KajsonDecoderError` loudly with dict context — mirroring the existing `BaseModel` branch (~line 265). No silent fall-through.
- [ ] **0.2** Add kajson round-trip tests in `../kajson/tests`: pydantic dataclass with (a) nested `BaseModel` field, (b) `Optional` field, (c) `list` of pydantic dataclasses, (d) `timedelta` field, (e) a subclass (type preservation); plus a negative test that a bad payload raises `KajsonDecoderError` (not silent corruption). Lock encode-via-`__dict__` with an explicit assertion rather than relying on the catch-all.
- [ ] **0.3** Bump kajson version in `../kajson/pyproject.toml` + add a CHANGELOG entry (genuine new capability, benefits all kajson users).

### Layer 2 — the converter (`pipelex/temporal/temporal_data_converter.py`)

Widen two predicates; leave the `BaseModel` path byte-identical.

- [ ] **0.4** `to_payload` (~line 56): factor `_is_kajson_wire_value(value) -> bool` = `isinstance(value, BaseModel) or is_pydantic_dataclass(type(value))`; route both single-value and first-element-of-list cases through kajson when it holds. `BaseModel` check first (hot-path short-circuit). The `__kajson_class_source__` lookup stays (it's `None` for dataclasses — harmless).
- [ ] **0.5** `from_payload` (~line 138): factor `_is_kajson_type(tp) -> bool` = `BaseModel` subclass **or** `is_pydantic_dataclass(tp)`; reuse it in all three hint checks (scalar, `Optional`, `list`). `_restore_class_source` only fires when `class_source_code is not None` (BaseModel-only), so dataclasses correctly skip it.

Perf note: adds one cheap `is_pydantic_dataclass()` check per conversion, behind the `BaseModel` short-circuit. Negligible; no benchmark needed (changes no existing payload).

### Test perimeter (three layers — most safety-critical seam)

- [ ] **0.6** Converter unit round-trip: call `to_payload` / `from_payload` directly for a pydantic dataclass and for `Optional[...]` / `list[...]` hints; assert value + concrete type survive. **Regression guard:** assert a `BaseModel` payload is byte-identical to before (the untouched path).
- [ ] **0.7** Temporal integration round-trip: a `@workflow.defn` / `@activity.defn` taking and returning a pydantic dataclass, exercised through the in-process test server (`tests/integration/pipelex/temporal/`).

### Cross-repo wiring

This worktree's `uv.lock` pins kajson as `{ editable = "../kajson" }` (confirmed) — changes in `../kajson` are picked up live, no publish needed for dev/test. `pipelex/pyproject.toml` still declares `kajson==0.5.0`; that specifier only bites at pipelex release time.

- [ ] **0.8** After 0.4/0.5 land, update the "Safety boundary" heading wording in this file from "must be BaseModel" framing to the now-true "BaseModel or pydantic dataclass" (already drafted above — just confirm it matches what shipped).
- [ ] **0.9** Verify the editable kajson install survives any `uv sync` run during this phase (re-check `uv.lock` line for `editable = "../kajson"`).

**Verify Phase 0:** kajson dataclass tests green · converter unit round-trip green (incl. BaseModel-unchanged regression guard) · `.venv/bin/pytest tests/integration/pipelex/temporal/` green · `make agent-check` + `make tb` clean.

> 🛑 **HARD STOP 1 — Converter generalized.** Foundation in place across two repos; wire rule is now "BaseModel or pydantic dataclass." Run the context-save protocol and END THE SESSION. The off-wire refactor (Phases 1–5) builds on top without depending on Phase 0's internals, so a fresh session can pick up cleanly. **Release-gate to record (not dev-blocking):** publish the new kajson to PyPI + bump the `kajson==` pin in `pipelex/pyproject.toml` before pipelex ships a release depending on the new feature.

---

## Phase 1 — Capture perf baseline (no production code changes)

- [ ] **1.1** Write the microbench harness at `tests/perf/test_dataclass_forms_bench.py` (sketch in "Perf harness reference" below). Prefer `pytest-benchmark` if it's already a dev dep (check `pyproject.toml`); else a committed `timeit` bench so the baseline is reproducible dependency-free.
- [ ] **1.2** Run on pre-change HEAD, save `tests/perf/baselines/dataclass_refactor_pre.json`.

What to measure: construction cost (N instances), validation cost (`model_validate` vs plain NamedTuple construction), serialize round-trip (`model_dump_json` / `model_validate_json` to mirror the converter), memory (`getsizeof` + `__dict__` vs `__slots__`, large-list growth). Perf-relevant sites: `DispatchOptions` (per-dispatch hot path — the one conversion that could regress), `PipeRunArg` (wire anchor, no form change), `_ThinkingParams` (control, no form change). The NamedTuple conversions (Phase 2) and Phase 0 are perf-neutral.

---

## Phase 2 — NamedTuple upgrades (off-wire bare-tuple returns, lowest risk)

Verified-to-exist bare-tuple returns where named fields prevent positional swaps. All off the wire, already-typed, no validation needed → NamedTuple (not pydantic dataclass). Replace `from typing import Tuple` annotations; keep `NamedTuple` defs module-local next to the function (or shared where two siblings return the same shape).

- [ ] **2.1** `_handle_basic_blueprint` (~line 336) + `_handle_refines` (~line 377) in `pipelex/core/concepts/concept_factory.py` — both return `(structure_class_name, refine_string)` with `refine_string: str | None`. Define ONE shared NamedTuple (e.g. `StructureNameAndRefine`) and reuse for both.
- [ ] **2.2** `split_cross_package_ref` (~line 197) in `pipelex/core/qualified_ref.py` — `(alias, remainder)`. Define e.g. `CrossPackageRef(alias, remainder)`. All call sites (`qualified_ref.py`, `core/domains/validation.py`, `core/concepts/concept_factory.py`, `core/concepts/validation.py`, `libraries/library.py`, `libraries/library_manager.py`, `libraries/pipe/pipe_library.py`, `libraries/concept/concept_library.py`) destructure into two locals — none relies on plain-tuple `len`/concat or passes the tuple onto a wire path. Safe.
- [ ] **2.3** `_get_is_prod_and_runtime_mode` in `pipelex/system/runtime_manager.py` — `(is_prod, runtime_mode)`. Single caller (`setup()`) unpacks positionally; NamedTuple supports positional unpacking, no breakage.
- [ ] **2.4** `_find_project_root` in `pipelex/config_manager.py` — `(project_root_dir, found_root_marker)`, `Tuple[Optional[Path], bool]`. NOTE: currently dead code (defined, never called) → zero call-site risk.

**Verify:** `make agent-check`; `make tb` (runtime_manager / config_manager touch boot paths). Temporal suite not required (nothing near the wire).

---

## Phase 3 — Off-wire stdlib dataclass removals (no wire, no hot-path concern)

HARD RULE 1: every stdlib `@dataclass` must go. These four are off-wire and not perf-critical.

- [ ] **3.1** `_EventLogContext` — `pipelex/reporting/reporting_manager.py` → **NamedTuple**. Fields `event_log: EventLogProtocol`, `workflow_id`, `pipeline_run_id`. Private manager state in `ReportingManager._event_log_contexts`, set wholesale + popped, never field-mutated, never serialized. `event_log` is a bare `@runtime_checkable` Protocol instance stored as-is. NamedTuple avoids needing `arbitrary_types_allowed`.
- [ ] **3.2** `ErrorPagesReport` — `pipelex/errors/error_pages_generator.py` → **frozen `BaseModel`**. Four `list[Path]` fields via `Field(default_factory=list)` + a computed `total` `@property`. Single full-kwargs construction, no in-place `.append` on instances → frozen holds. `Path` serializes natively in pydantic v2; the computed-property + default_factory pattern argues for BaseModel over NamedTuple.
- [ ] **3.3** `CustomClassInfo` — `pipelex/builder/runner_code.py` → **frozen `BaseModel`**. Scalar fields (`class_name`, `domain_code`, `concept_code`) + two computed `@property` (`module_name`, `import_statement`). Builder/codegen artifact, never mutated, never a Temporal arg/return. `builder/CLAUDE.md` says the builder layer is uniformly pydantic; the properties make NamedTuple awkward.
- [ ] **3.4** `VariableReference` — `pipelex/tools/jinja2/jinja2_required_variables.py` → **mutable (non-frozen) `BaseModel`** with `filters: list[str] = Field(default_factory=list)`. CRITICAL: it is MUTATED IN PLACE — `_collect_variable_references` does `references[full_path].filters.append(filter_name)` on re-seen variables. In-place mutation rules out NamedTuple and any frozen form. Do NOT freeze it. (low-medium risk: preserve the append-after-construction contract.)

**Verify:** `make agent-check` after each; `make tb` after the group.

---

## Phase 4 — Temporal-adjacent stdlib removal (low risk)

- [ ] **4.1** `RegistrationFailure` — `pipelex/temporal/tprl/namespace_check.py` (~line 50) → **NamedTuple**. Fields `namespace: str`, `missing: tuple[str, ...]`, `rpc_error_message: str`. Off-wire admin plumbing — produced by `ensure_required_search_attributes_registered` at worker boot/setup, consumed only by `pipelex/cli/commands/setup_temporal_namespace_cmd.py` to format a runbook; never an `@activity.defn` return nor a wire field. **Implementer note:** a NamedTuple is also a `tuple`, so all consumers must keep discriminating the `RegistrationFailure | tuple[str, ...]` return via `isinstance(x, RegistrationFailure)` (CLI already does, ~line 148), never `isinstance(x, tuple)`.

**Verify:** `make agent-check`; `make tb`; `.venv/bin/pytest tests/integration/pipelex/temporal/`.

> 🛑 **HARD STOP 2 — All mechanical off-wire work done.** NamedTuple upgrades + four off-wire stdlib removals + the temporal-adjacent one have landed; the only remaining conversion is the reviewed `DispatchOptions`, which needs a without-temporal-extra import check that's cleanest in a fresh session. Run the context-save protocol and END THE SESSION.

---

## Phase 5 — The reviewed item: `DispatchOptions` (needs human-review gate)

`DispatchOptions` — `pipelex/temporal/config_temporal.py` (~line 366) → **frozen `BaseModel`** with `model_config = ConfigDict(arbitrary_types_allowed=True)`. Off-wire (built only inside `WorkerConfig.resolve_dispatch`, immediately consumed by splatting `to_execute_kwargs()` into `workflow.execute_activity(...)`; never a workflow/activity arg/return, never a wire field). Holds a live `temporalio` `RetryPolicy` (non-JSON, `TYPE_CHECKING` forward ref) + the `to_execute_kwargs()` behavior method → `arbitrary_types_allowed` required, `frozen` matches the build-once-read-only lifecycle. NamedTuple/pydantic dataclass are wrong (the method + arbitrary SDK field; and a pydantic dataclass hits the SAME class-def-time annotation-resolution risk as BaseModel — Phase 0 does not change this).

**Load-bearing invariant (the gate):** the module must import without `temporalio` installed. `temporalio` is imported only under `TYPE_CHECKING` and lazily inside `make_retry_policy`; `retry_policy: "RetryPolicy"` is a forward ref. A pydantic model builds a validator at class-def time and may try to resolve that annotation, risking pulling `temporalio` into the plain import path.

- [ ] **5.1** GATE: verify the `temporalio`-not-installed import path — run `make tb` on an environment WITHOUT the temporal extra and confirm import + config-load succeed. Keep `RetryPolicy` under `TYPE_CHECKING` (or typed `Any`).
- [ ] **5.2** Convert `DispatchOptions` to frozen `BaseModel(arbitrary_types_allowed=True)`, preserving `to_execute_kwargs()`. If the import-clean path proves infeasible, FALL BACK to a NamedTuple with `timedelta | None` fields + the `to_execute_kwargs` method (still off-wire-legal) — record the decision in the Session log.

**Verify:** `make agent-check`; `make tb`; `.venv/bin/pytest tests/integration/pipelex/temporal/`.

---

## Phase 6 — Perf diff + final gate

- [ ] **6.1** Re-run the harness, save `tests/perf/baselines/dataclass_refactor_post.json`.
- [ ] **6.2** Diff pre vs post. Acceptance: NamedTuple/dataclass paths must not regress; `DispatchOptions` as frozen `BaseModel` may show a small per-dispatch validation cost — confirm it's negligible vs the (network-bound) activity round-trip it configures. If non-trivial in the loop → switch `DispatchOptions` to the NamedTuple fallback (5.2) and re-verify.
- [ ] **6.3** Final gate: `grep -rln "from dataclasses import" pipelex/` returns nothing · full `make agent-check` · full `.venv/bin/pytest tests/integration/pipelex/temporal/` · `make agent-test`.
- [ ] **6.4** Record the release-time follow-up (still pending): publish new kajson to PyPI + bump the `kajson==` pin in `pipelex/pyproject.toml`.

> 🛑 **HARD STOP 3 — Done.** Converter + kajson generalized (wire rule now BaseModel-or-pydantic-dataclass), all stdlib dataclasses removed, NamedTuple upgrades landed, perf diff acceptable, temporal suite green, denylist types never converted away from BaseModel. Run the context-save protocol; final Session log entry records the perf diff, Phase 0 test results, the `DispatchOptions` import-invariant outcome, and the pending release-gate.

---

## Leave-as-is (do NOT convert) — confirmed correct already

- `_ThinkingParams` — `pipelex/plugins/anthropic/anthropic_llm_worker.py` — the codebase's one legitimate pydantic dataclass; off-wire, built+consumed within a single `_gen_text` call. Right tool already.
- `ResultFile` (`pipelex/pipe_run/delivery_executor.py`), `SupportCheck` (`pipelex/cogt/img_gen/img_gen_param_support.py`), `StoredData` (`pipelex/tools/storage/storage_provider_abstract.py`), `PipeJobComponents` (`pipelex/pipe_run/pipe_job_factory.py`) — existing off-wire NamedTuples, all correct. (`PipeJobComponents` is a local unpack container for building `PipeJob`; anything embedded INTO `PipeJob` must still be wire-legal.)
- `iter_model_fields` (`pipelex/tools/misc/model_utils.py`, `pipelex/tools/typing/field_helpers.py`) and `items` (`pipelex/tools/misc/func_registry.py`) — keep as plain `Iterator[Tuple[...]]` (`dict.items()` convention). Best follow-up (separate refactor) is consolidating the two duplicate `iter_model_fields`, not changing their data form.
- `generate_from_structure_blueprint` (`pipelex/core/concepts/structure_generation/generator.py` ~line 78) — `(class_code, generated_class)`; one element is a live `type`. Firmly off-wire (a `type` can't round-trip the converter). NamedTuple would be harmless polish but optional — leave unless doing a broader codegen cleanup.

## Rejected — stale candidates that do NOT exist (do not re-propose)

Verified absent by full-tree grep + directory listing. Listed so a future session doesn't re-derive them: `pipelex/cli/run_helpers.py` (`execute_method_and_output`, `_resolve_inputs_and_memory`); `pipelex/cli/ui_helpers.py` (`prompt_for_methods_and_output`); `pipelex/cli/blueprint_writer.py` (the four `_write_*_stub_file`); the entire `pipelex/pipe_operators/ocr/` path; `pipe_func._resolve_content_generator_and_func_name`; `pipe_img_gen_factory._resolve_blueprint_and_factory`; `pipe_llm_blueprint._split_prompt_template`; `pipe_llm_factory._resolve_prompt_template_and_target`; `toml_utils.load_toml_from_path_and_get_content`; `template_provider_abstract._provide_template_text_and_source`; `file_utils._split_filepath_into_components(_with_extension)`; `hub.get_pipelex_hub_and_pipe_router`; `sub_pipe._resolve_condition_expression`; `library_manager.get_library_paths`; `concept_native.NativeConceptClassNamePair`; `concept_factory._parse_concept_string`; `stuff_factory.make_from_str` (returns a single `Stuff`, misdescribed); the removed `pipelex/cocktail/` directory (`_detect_action_type_and_agent`, `_parse_command_line`). The nearest real shape to the gone `blueprint_writer` is `structures_cmd._generate_structures_for_inline` returning `list[tuple[str, str]]` — a weak list-element case, separately scoped; do not fold the non-existent functions into it.

---

## Perf harness reference

Place at `tests/perf/test_dataclass_forms_bench.py`:

```python
import sys
import timeit
from datetime import timedelta
from typing import NamedTuple, Optional

from pydantic import BaseModel, ConfigDict


class DispatchOptionsBM(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    task_queue: str
    start_to_close_timeout: Optional[timedelta] = None
    schedule_to_close_timeout: Optional[timedelta] = None
    retry_policy: Optional[object] = None  # stand-in for temporalio RetryPolicy


class DispatchOptionsNT(NamedTuple):
    task_queue: str
    start_to_close_timeout: Optional[timedelta] = None
    schedule_to_close_timeout: Optional[timedelta] = None
    retry_policy: Optional[object] = None


N = 200_000


def _bench(label, fn):
    secs = timeit.timeit(fn, number=N)
    print(f"{label:40s} {secs / N * 1e9:8.1f} ns/op  ({secs:.3f}s / {N})")


def main():
    tq = "default"
    to = timedelta(seconds=30)
    _bench("construct BaseModel", lambda: DispatchOptionsBM(task_queue=tq, start_to_close_timeout=to))
    _bench("construct NamedTuple", lambda: DispatchOptionsNT(task_queue=tq, start_to_close_timeout=to))
    bm = DispatchOptionsBM(task_queue=tq, start_to_close_timeout=to)
    payload = bm.model_dump()
    _bench("BaseModel model_dump", lambda: bm.model_dump())
    _bench("BaseModel model_validate", lambda: DispatchOptionsBM.model_validate(payload))
    _bench("BaseModel json round-trip", lambda: DispatchOptionsBM.model_validate_json(bm.model_dump_json()))
    print("\n--- memory (single instance) ---")
    print("BaseModel getsizeof:", sys.getsizeof(bm), "has __dict__:", hasattr(bm, "__dict__"))
    nt = DispatchOptionsNT(task_queue=tq, start_to_close_timeout=to)
    print("NamedTuple getsizeof:", sys.getsizeof(nt), "has __dict__:", hasattr(nt, "__dict__"))


if __name__ == "__main__":
    main()
```

For the wire anchor, add a second bench constructing a realistic `PipeRunArg` (or a stripped stand-in matching its field count) and timing `model_dump_json()` / `model_validate_json()` — the reference for asserting no wire type accidentally got heavier.

---

## Session log (newest first)

Append one entry per session, especially at every hard stop. Template:

```
### YYYY-MM-DD — <phase / what this session covered>
- Landed: <checkboxes flipped + one-line results>
- Decisions: <any choice taken, with reason>
- Open questions: <anything unresolved for the next session>
- Code state: <clean & committed? mid-edit? which files dirty?>
- NEXT ACTION: <the single exact thing the next session should do first>
```

### 2026-05-29 — Ledger created (planning only, no code changes)
- Landed: nothing implemented yet. This ledger was created from the former `wip/data-class-best-practices-plan.md` (removed). The previous root ledger (`feature/API-readiness-4`, all complete) was archived to `wip/error-handling/archive-todos-api-readiness-4.md`.
- Decisions: (1) per-site type strategy for the six stdlib dataclasses — NOT a uniform pydantic-dataclass conversion. (2) Generalize the converter + kajson FIRST as Phase 0, scoped to pydantic dataclasses only. (3) kajson is consumed editable from `../kajson` in this worktree, so no PyPI publish needed for dev; publish + pin bump is a release-time gate.
- Open questions: none blocking. The `DispatchOptions` import-without-temporalio invariant (Phase 5) is the one real unknown — gated by 5.1.
- Code state: clean working tree except this ledger + the archived file move. No production code touched.
- NEXT ACTION: start Phase 0 — Pre-flight boundary freeze, then task 0.1 (kajson `is_pydantic_dataclass` decode branch in `../kajson/kajson/json_decoder.py`), TDD: write the kajson round-trip tests (0.2) first.
