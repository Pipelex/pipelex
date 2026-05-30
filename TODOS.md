# Data-Class Best-Practices Refactor — Working Ledger (`refactor/Dataclasses`)

Give every data holder the right shape. Eradicate every stdlib `@dataclass` (HARD RULE 1) — but replace it with whichever form fits the site, NOT uniformly with `BaseModel`.

**On the Temporal wire:** `BaseModel` or (after Phase 0) a pydantic dataclass — the two forms `BaseModelPayloadConverter` routes through kajson with type preservation.

**Off the wire, choose per-site** (this is the premise — pydantic dataclass is a first-class option here, often the lowest-churn one):

- **`NamedTuple`** — a small fixed immutable record replacing a bare tuple. Also the only safe form when a field is a bare `@runtime_checkable` Protocol / arbitrary non-pydantic type, because it skips validation (no `arbitrary_types_allowed` dance). Avoid when the type is returned in a union alongside a real `tuple` (a NamedTuple *is* a tuple → ambiguous `isinstance`).
- **pydantic dataclass** (`from pydantic.dataclasses import dataclass`) — a validated record that wants to keep dataclass idioms (`field(default_factory=...)`, computed `@property`, `frozen=`) with **minimal churn** (often just swap the decorator import). Wire-legal since Phase 0. **Use it ONLY for internal records that are constructed + field-read and never serialized.** A pydantic dataclass has no `.model_dump()` / `.model_validate()` methods — and "does this ever need serializing/dumping?" is the *deciding* question, not an afterthought: **if it ever needs dumping, make it a `BaseModel` from the start — do NOT reach for `TypeAdapter`.** Needing `TypeAdapter` means the wrong shape was picked; keep `TypeAdapter` out of the codebase entirely.
- **frozen `BaseModel`** — an immutable validated value object that needs the full model API (`model_dump`, validators, discriminated unions) OR sits in a layer that is uniformly `BaseModel` (e.g. `pipelex/builder/`), OR must stay type-distinct from a sibling `tuple` in a union return.
- **plain mutable `BaseModel`** — genuinely mutated in place AND wants the model API / layer-consistency; otherwise a non-frozen pydantic dataclass is the lighter choice for in-place-mutated records.

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

- [x] Re-confirm the wire layer is clean: `grep -rn "@dataclass\|NamedTuple" pipelex/temporal/` returns nothing.
  - Result: only two matches, both off-wire and slated for later phases — `config_temporal.py:366` (`DispatchOptions`, Phase 5) and `tprl/namespace_check.py:50` (`RegistrationFailure`, Phase 4). No *wire* type is a dataclass/NamedTuple.
- [x] Resolve every "confirm path" entry in the safety boundary above (`GraphContext`, `LibraryCrate`, `PipeAbstract`, `PageContent`, page-view payload, `TraceEvent`) and pin the paths.
  - Result (all `BaseModel`): `GraphContext`=`pipelex/graph/graph_context.py:12`; `LibraryCrate`=`pipelex/libraries/library_crate.py:11`; `PipeAbstract`=`pipelex/core/pipes/pipe_abstract.py:46`; `PageContent`=`pipelex/core/stuffs/page_content.py:13` (StructuredContent); page-view payload = `PageContent.page_view: ImageContent | None` (line 15) → already-listed `ImageContent`; `TraceEvent`=`pipelex/tracing/trace_events.py:34`.

---

## Phase 0 — Generalize the converter (+ kajson) to accept pydantic dataclasses

Goal: stop the converter from being the sole arbiter of domain-model shape. Today `BaseModelPayloadConverter` routes only `BaseModel` / `Optional[BaseModel]` / `list[BaseModel]` through kajson; everything else falls through to Temporal's stock JSON. Phase 0 widens that to pydantic dataclasses (and `Optional` / `list` of them). Scope is pydantic dataclasses ONLY — `NamedTuple` stays out (kajson flattens it to a bare JSON array, losing field names + type), stdlib dataclasses stay out (HARD RULE 1 eradicates them), arbitrary classes stay out (unsafe `__dict__`-replace path).

### Layer 1 — kajson (`../kajson`, editable via this worktree's `uv.lock`)

kajson v0.5.0 has no dataclass support and no dataclass tests. A pydantic dataclass currently only survives via the untested generic catch-all: encode via `__dict__` (`json_encoder.py` ~160), decode via `the_class(**the_dict)` (`json_decoder.py` ~293). The decode path is fragile — if validation raises there, the next line swallows it (`except Exception: pass`) and falls through to the unsafe `obj.__dict__ = the_dict` path, then to returning a raw dict. Silent corruption instead of a loud error.

- [x] **0.1** Add an explicit pydantic-dataclass branch in `_apply_decoder_strategies` (after the `Enum` / `BaseModel` branches, before the generic constructor), using `pydantic.dataclasses.is_pydantic_dataclass`. Reconstruct via the dataclass' pydantic validator (validates), and on `ValidationError` raise `KajsonDecoderError` loudly with dict context — mirroring the existing `BaseModel` branch (~line 265). No silent fall-through.
  - Result: added `is_pydantic_dataclass` import + the branch in `../kajson/kajson/json_decoder.py` (`return the_class(**the_dict)`, `except ValidationError → raise KajsonDecoderError(...) from exc`). Confirmed the prior behavior was silent corruption (bad dataclass payload returned a raw `dict`); now raises loudly.
- [x] **0.2** Add kajson round-trip tests in `../kajson/tests`: pydantic dataclass with (a) nested `BaseModel` field, (b) `Optional` field, (c) `list` of pydantic dataclasses, (d) `timedelta` field, (e) a subclass (type preservation); plus a negative test that a bad payload raises `KajsonDecoderError` (not silent corruption). Lock encode-via-`__dict__` with an explicit assertion rather than relying on the catch-all.
  - Result: `../kajson/tests/unit/test_pydantic_dataclass.py` (7 tests, all cases above + encode-via-`__dict__` metadata assertion + negative test). The negative test was the TDD red (DID NOT RAISE before 0.1, green after). Full kajson suite green (257 passed, 1 skipped); kajson `make agent-check` clean.
  - Follow-up from code review: the timedelta round-trip initially needed a band-aid (an earlier suite test, `test_json_encoder`, clears the process-global codec registry without restoring). Fixed the **root cause** instead — `test_json_encoder.py` / `test_json_decoder.py` autouse fixtures now snapshot the registry and restore it on teardown — and removed the band-aid. The new dataclass tests are order-independent without re-registering anything.
- [x] **0.3** Bump kajson version in `../kajson/pyproject.toml` + add a CHANGELOG entry (genuine new capability, benefits all kajson users).
  - Result: `0.5.0` → `0.6.0` + dated CHANGELOG entry. kajson is on its own `feature/Support-more-types` branch (versioned-only CHANGELOG convention — no `[Unreleased]`). Editable install means the pipelex venv serves the live source; installed metadata stays `0.5.0`, so the pipelex `kajson==0.5.0` pin is still satisfied. **Do NOT run `uv lock`/`uv sync` in this worktree until the pin is bumped** — the `==0.5.0` exact pin would conflict with the editable `0.6.0`. Pin bump stays bundled with the PyPI publish at the release gate (below).

### Layer 2 — the converter (`pipelex/temporal/temporal_data_converter.py`)

Widen two predicates; leave the `BaseModel` path byte-identical.

- [x] **0.4** `to_payload` (~line 56): factor `_is_kajson_wire_value(value) -> bool` = `isinstance(value, BaseModel) or is_pydantic_dataclass(type(value))`; route both single-value and first-element-of-list cases through kajson when it holds. `BaseModel` check first (hot-path short-circuit). The `__kajson_class_source__` lookup stays (it's `None` for dataclasses — harmless).
  - Result: added `_is_kajson_wire_value(value: object)` + extracted `_kajson_to_payload(value, source_type_holder)` (shared by the scalar and list branches) + `_first_kajson_list_element` (list probe). BaseModel path is byte-identical (locked by the 0.6 regression guard). **Type-checking deviation:** the original relied on inline `isinstance` narrowing; the predicate is non-narrowing, so to keep pyright-strict `reportUnknownArgumentType` happy I typed the value predicate param as `object` (so `type(value)` is `type[object]`, not `type[Unknown]`) and kept `value` explicitly `Any` at call sites.
- [x] **0.5** `from_payload` (~line 138): factor `_is_kajson_type(tp) -> bool` = `BaseModel` subclass **or** `is_pydantic_dataclass(tp)`; reuse it in all three hint checks (scalar, `Optional`, `list`). `_restore_class_source` only fires when `class_source_code is not None` (BaseModel-only), so dataclasses correctly skip it.
  - Result: added `_is_kajson_type(type_hint)`, generalized `_unwrap_optional_base_model` → `_unwrap_optional_kajson_type`, and reused `_is_kajson_type` in all three checks (scalar, Optional, list). `is_pydantic_dataclass` is runtime-safe on non-class hints (returns `False`), so the inner `Optional`/`list` args need no guard. One `cast("Any", type_hint)` collapses the post-`isinstance` `Any | type[Unknown]` for the typed probe.

Perf note: adds one cheap `is_pydantic_dataclass()` check per conversion, behind the `BaseModel` short-circuit. Negligible; no benchmark needed (changes no existing payload).

### Test perimeter (three layers — most safety-critical seam)

- [x] **0.6** Converter unit round-trip: call `to_payload` / `from_payload` directly for a pydantic dataclass and for `Optional[...]` / `list[...]` hints; assert value + concrete type survive. **Regression guard:** assert a `BaseModel` payload is byte-identical to before (the untouched path).
  - Result: `tests/integration/pipelex/temporal/data_converter/test_data_conv_dataclass.py` — scalar / `X | None` / `list[X]` dataclass round-trips (concrete type + nested BaseModel preserved) + a byte-identical guard for a plain BaseModel (metadata == `{encoding}`, data == `kajson.dumps(model)`). 8 tests in the dir pass.
- [x] **0.7** Temporal integration round-trip: a `@workflow.defn` / `@activity.defn` taking and returning a pydantic dataclass, exercised through the in-process test server (`tests/integration/pipelex/temporal/`).
  - Result: `tests/integration/pipelex/temporal/test_wf_dataclass_roundtrip.py` — `WfEchoDataclassPayload` forwards a `@pydantic_dataclass` (with nested BaseModel + `timedelta` fields) through an activity via `WorkflowEnvironment.start_local` + `Worker`; asserts type preserved end-to-end. Green. Broader temporal integration suite (non-inference) re-run clean: 136 passed, 4 pre-existing xdist-race xpass, no regressions.

### Cross-repo wiring

This worktree's `uv.lock` pins kajson as `{ editable = "../kajson" }` (confirmed) — changes in `../kajson` are picked up live, no publish needed for dev/test. `pipelex/pyproject.toml` still declares `kajson==0.5.0`; that specifier only bites at pipelex release time.

- [x] **0.8** After 0.4/0.5 land, update the "Safety boundary" heading wording in this file from "must be BaseModel" framing to the now-true "BaseModel or pydantic dataclass" (already drafted above — just confirm it matches what shipped).
  - Result: confirmed — the heading and body wording ("each MUST be a `BaseModel` **or** a pydantic dataclass — the two forms `BaseModelPayloadConverter` routes through kajson") matches what shipped (`_is_kajson_wire_value` / `_is_kajson_type` route both forms through kajson). No edit needed.
- [x] **0.9** Verify the editable kajson install survives any `uv sync` run during this phase (re-check `uv.lock` line for `editable = "../kajson"`).
  - Result: `uv.lock` still pins `source = { editable = "../kajson" }` (line 1972); no `uv lock`/`uv sync` was run. Verified the pipelex worktree's `.venv` serves the live kajson source (imports the new decode branch; bad payload raises `KajsonDecoderError`) with installed metadata still `0.5.0`. **Caveat:** a `uv lock` regeneration WOULD now conflict (editable `0.6.0` vs `kajson==0.5.0` pin) — defer until the release-gate pin bump.

**Verify Phase 0:** kajson dataclass tests green · converter unit round-trip green (incl. BaseModel-unchanged regression guard) · `.venv/bin/pytest tests/integration/pipelex/temporal/` green · `make agent-check` + `make tb` clean.

> 🛑 **HARD STOP 1 — Converter generalized.** Foundation in place across two repos; wire rule is now "BaseModel or pydantic dataclass." Run the context-save protocol and END THE SESSION. The off-wire refactor (Phases 1–5) builds on top without depending on Phase 0's internals, so a fresh session can pick up cleanly. **Release-gate to record (not dev-blocking):** publish the new kajson to PyPI + bump the `kajson==` pin in `pipelex/pyproject.toml` before pipelex ships a release depending on the new feature.

---

## Phase 1 — ~~Capture perf baseline~~ → DROPPED after review (no production code changes either way)

**The whole perf-measurement effort (this phase + Phase 6's perf diff) was BUILT, then DROPPED on review (user decision, 2026-05-29).** The harness (`tests/perf/test_dataclass_forms_bench.py` + `tests/perf/baselines/dataclass_refactor_pre.json`) was deleted.

Why it measured nothing useful:

- It benchmarked **synthetic stand-ins**, not the real classes. The `DispatchOptions*` stand-ins matched the real field shape, but the "wire anchor" was a fake type that timed pydantic's native `model_dump_json`/`model_validate_json` — **NOT** the real Temporal wire path (`BaseModelPayloadConverter` → kajson with type-preservation metadata). So the one number meant to guard "no wire type got heavier" never touched the actual wire code.
- The costs are **negligible in context**: the only conversion that could plausibly regress is `DispatchOptions` (one build per activity dispatch, ~360ns form-delta) — dwarfed by the 10²–10³ ms network round-trip of the activity it configures.
- **None of the Phase 2/3/4 conversions sit on a hot path** (build-time, per-usage-event, dev-CLI, template-prep, worker-boot), so their construction speed never shows up in real behavior.

Consequence for the `DispatchOptions` form decision (Phase 5): it now rests on **reasoning** (per-dispatch cost is negligible vs the network round-trip), not measurement — no perf data is needed to accept frozen `BaseModel`.

- [x] **1.1 / 1.2** — built the harness + captured the pre-change baseline, then **removed both** per the review above.

---

## Phase 2 — NamedTuple upgrades (off-wire bare-tuple returns, lowest risk)

Verified-to-exist bare-tuple returns where named fields prevent positional swaps. All off the wire, already-typed, no validation needed → NamedTuple (not pydantic dataclass). Replace `from typing import Tuple` annotations; keep `NamedTuple` defs module-local next to the function (or shared where two siblings return the same shape).

- [x] **2.1** `_handle_basic_blueprint` (~line 336) + `_handle_refines` (~line 377) in `pipelex/core/concepts/concept_factory.py` — both return `(structure_class_name, refine_string)` with `refine_string: str | None`. Define ONE shared NamedTuple (e.g. `StructureNameAndRefine`) and reuse for both.
  - Result: added module-level `class StructureNameAndRefine(NamedTuple)` with `structure_class_name: str`, `refine_string: str | None`. Both methods now return it (6 return sites wrapped: 4 in `_handle_basic_blueprint`, 2 in `_handle_refines`). `_handle_refines`'s refine widened from `str` → `str | None` (its sole caller passes straight to `Concept.refines: str | None`, so type-safe). All 3 call sites use positional unpacking — unchanged. Confirmed `Concept.refines` is `str | None`.
- [x] **2.2** `split_cross_package_ref` (~line 197) in `pipelex/core/qualified_ref.py` — `(alias, remainder)`. Define e.g. `CrossPackageRef(alias, remainder)`. All call sites (`qualified_ref.py`, `core/domains/validation.py`, `core/concepts/concept_factory.py`, `core/concepts/validation.py`, `libraries/library.py`, `libraries/library_manager.py`, `libraries/pipe/pipe_library.py`, `libraries/concept/concept_library.py`) destructure into two locals — none relies on plain-tuple `len`/concat or passes the tuple onto a wire path. Safe.
  - Result: added module-level `class CrossPackageRef(NamedTuple)` with `alias: str`, `remainder: str`; `split_cross_package_ref` now returns `CrossPackageRef(alias=..., remainder=...)`. Re-grepped ALL 12 current call sites (the plan's list was close but I verified against the live tree) — every one uses positional 2-tuple unpacking (`alias, remainder = ...` or `_, remainder = ...`), so none changed. Core+pipes suite green (1323 passed).
- [x] **2.3** ~~`_get_is_prod_and_runtime_mode` in `pipelex/system/runtime_manager.py`~~ — **DOES NOT EXIST in current tree (skipped).** There is no `runtime_manager.py`; runtime mode lives in `pipelex/system/runtime.py` and is now fully **property-based** on a `RuntimeManager(BaseModel)` (`is_unit_testing`, `is_ci_testing`, `environment`, `run_mode` props) — no `(is_prod, runtime_mode)` tuple helper anywhere (grep-confirmed). The stale audit predates that refactor. Nothing to convert.
- [x] **2.4** ~~`_find_project_root` in `pipelex/config_manager.py`~~ — **DOES NOT EXIST in current tree (skipped).** `config_manager.py` is now `pipelex/system/configuration/config_loader.py` (`config_manager = ConfigLoader()`); its `find_project_root(start_dir) -> Path | None` returns just `Path | None` — the `found_root_marker` bool was dropped in the refactor, so there is no `(Path, bool)` tuple to convert (grep-confirmed no such tuple anywhere).

**Verify:** `make agent-check`; `make tb` (runtime_manager / config_manager touch boot paths). Temporal suite not required (nothing near the wire).
  - Result: `make agent-check` clean (pyright 0/0, mypy 1932 files); `make tb` 2 passed; targeted `tests/unit|integration/pipelex/core/` + `tests/integration/pipelex/pipes/` → 1323 passed, 1 xfailed (pre-existing known-bug marker).

---

## Phase 3 — Off-wire stdlib dataclass removals (no wire, no hot-path concern)

HARD RULE 1: every stdlib `@dataclass` must go. These four are off-wire and not perf-critical. Form chosen per-site per the form-selection guide at the top of this file — **including pydantic dataclass**, which for records already written in dataclass style (`field(default_factory=...)` + computed `@property`) is the lowest-churn replacement (just swap the decorator import).

- [x] **3.1** `_EventLogContext` — `pipelex/reporting/reporting_manager.py` → **NamedTuple**. Fields `event_log: EventLogProtocol`, `workflow_id`, `pipeline_run_id`. Private manager state in `ReportingManager._event_log_contexts`, set wholesale + popped, never field-mutated, never serialized. `event_log` is a bare `@runtime_checkable` Protocol instance stored as-is. NamedTuple avoids needing `arbitrary_types_allowed`.
  - Result: `@dataclass\nclass _EventLogContext` → `class _EventLogContext(NamedTuple)`; removed the now-unused `from dataclasses import dataclass`. Confirmed all uses are kwargs-construction (line ~90), dict store/pop, and attribute reads (`context.event_log.next_sequence()`, `.pipeline_run_id`, `.workflow_id`, `.event_log.emit(...)`) — no field mutation. Reporting unit suite green.
- [x] **3.2** `ErrorPagesReport` — `pipelex/errors/error_pages_generator.py` → **frozen `BaseModel`**. Four `list[Path]` fields via `Field(default_factory=list)` + a computed `total` `@property`. ~~Single full-kwargs construction, no in-place `.append` on instances → frozen holds.~~ `Path` serializes natively in pydantic v2; the computed-property + default_factory pattern argues for BaseModel over NamedTuple.
  - Result (FINAL, after 2nd review pass): **frozen pydantic dataclass** (`@pydantic.dataclasses.dataclass(frozen=True)`, `field(default_factory=list[Path])` ×4 + the `total` `@property`). This is the near-zero-diff replacement of the original `@dataclass(frozen=True)` — just swapped `from dataclasses import dataclass` → `from pydantic.dataclasses import dataclass` (kept `from dataclasses import field`). It's a dev-tool report with no model-API need, so a pydantic dataclass fits better than `BaseModel` (which I'd used in the first pass — reverted). **DEVIATION from plan rationale (still applies):** the plan claimed "single full-kwargs construction, no in-place `.append`" — STALE: it's built empty (`ErrorPagesReport()`) then **appended in place** (`_commit_page`/`_remove_orphans`). `frozen=True` (stdlib dataclass, pydantic dataclass, AND BaseModel) blocks attribute *reassignment*, NOT list mutation — `.append` works under all. Errors suite + type_uri-uniqueness test green (318 passed in the errors+jinja2+templating run).
- [x] **3.3** `CustomClassInfo` — `pipelex/builder/runner_code.py` → **frozen `BaseModel`**. Scalar fields (`class_name`, `domain_code`, `concept_code`) + two computed `@property` (`module_name`, `import_statement`). Builder/codegen artifact, never mutated, never a Temporal arg/return. `builder/CLAUDE.md` says the builder layer is uniformly pydantic; the properties make NamedTuple awkward.
  - Result: `@dataclass` → `class CustomClassInfo(BaseModel)` with `model_config = ConfigDict(frozen=True)`; both properties kept; removed `from dataclasses import dataclass`. Confirmed all uses are kwargs-construction (line ~116) + attribute reads + use as `dict[str, CustomClassInfo]` values — no field mutation, no instance hashing relied upon (frozen makes it hashable anyway, a superset). Builder suite green.
- [x] **3.4** `VariableReference` — `pipelex/tools/jinja2/jinja2_required_variables.py` → **mutable (non-frozen) `BaseModel`** with `filters: list[str] = Field(default_factory=list)`. CRITICAL: it is MUTATED IN PLACE — `_collect_variable_references` does `references[full_path].filters.append(filter_name)` on re-seen variables. In-place mutation rules out NamedTuple and any frozen form. Do NOT freeze it. (low-medium risk: preserve the append-after-construction contract.)
  - Result (FINAL, after 2nd review pass): **non-frozen pydantic dataclass** (`@pydantic.dataclasses.dataclass`, `path: str` + `filters: list[str] = field(default_factory=list[str])`). Near-zero-diff replacement of the original `@dataclass` — swapped `from dataclasses import dataclass` → `from pydantic.dataclasses import dataclass` (kept `field`), and used `list[str]` as the factory so no `# pyright: ignore` is needed (the original had one). Chosen over `BaseModel` (first pass — reverted): it's mutated in place and has no model-API need, so a pydantic dataclass is the lighter, more idiomatic fit. Confirmed the in-place `.filters.append(...)` works (pydantic dataclasses don't validate on attribute access/mutation, only on init). jinja2 var-ref unit tests + templating pipeline green.

**Verify:** `make agent-check` after each; `make tb` after the group.
  - Result: `make agent-check` clean (pyright 0/0, mypy 1932 files); `make tb` 2 passed; targeted `builder` + `tools` + `errors` + `reporting` suites → 1676 passed, 1 pre-existing skip.

---

## Phase 4 — Temporal-adjacent stdlib removal (low risk)

- [x] **4.1** `RegistrationFailure` — `pipelex/temporal/tprl/namespace_check.py` (~line 50) → **NamedTuple**. Fields `namespace: str`, `missing: tuple[str, ...]`, `rpc_error_message: str`. Off-wire admin plumbing — produced by `ensure_required_search_attributes_registered` at worker boot/setup, consumed only by `pipelex/cli/commands/setup_temporal_namespace_cmd.py` to format a runbook; never an `@activity.defn` return nor a wire field. **Implementer note:** a NamedTuple is also a `tuple`, so all consumers must keep discriminating the `RegistrationFailure | tuple[str, ...]` return via `isinstance(x, RegistrationFailure)` (CLI already does, ~line 148), never `isinstance(x, tuple)`.
  - Result: `@dataclass(frozen=True)` → **frozen `BaseModel`** (`model_config = ConfigDict(frozen=True)`). **DEVIATION from the plan's NamedTuple target — deliberately chose BaseModel over NamedTuple here** (decided on review, 2026-05-29): the return type is a union `RegistrationFailure | tuple[str, ...]`, and a NamedTuple IS a tuple, so a NamedTuple form makes BOTH arms tuples and leans entirely on every caller using `isinstance(x, RegistrationFailure)`. A `BaseModel` is **not** a tuple, so it stays cleanly type-distinct from the `tuple[str, ...]` success arm — strictly safer for this union. Its fields (`str`, `tuple[str, ...]`, `str`) are all pydantic-native, so NO `arbitrary_types_allowed` is needed. (A frozen *pydantic dataclass* would also have worked and been an even smaller diff — noted as the minimal-churn alternative.) Verified all consumers: 3 discrimination sites use `isinstance(..., RegistrationFailure)` (`setup_temporal_namespace_cmd.py:148`, `test_ensure_search_attributes_registered.py:117/140`, `integration/.../conftest.py:156`); none uses `isinstance(x, tuple)`; field access is `.namespace`/`.missing`/`.rpc_error_message`; construction is kwargs. Temporal unit+integration + setup-namespace CLI tests green (452 passed, 4 pre-existing xpass).

**Verify:** `make agent-check`; `make tb`; `.venv/bin/pytest tests/integration/pipelex/temporal/`.
  - Result: `make agent-check` clean; `make tb` 2 passed; `tests/unit/pipelex/temporal/` + `tests/integration/pipelex/temporal/` → 445 passed, 4 xpassed (the documented pre-existing xdist class-registration race flakes — passes in isolation; no regressions). No stray temporal processes after the run.

> 🛑 **HARD STOP 2 — All mechanical off-wire work done.** NamedTuple upgrades + four off-wire stdlib removals + the temporal-adjacent one have landed; the only remaining conversion is the reviewed `DispatchOptions`, which needs a without-temporal-extra import check that's cleanest in a fresh session. Run the context-save protocol and END THE SESSION.

---

## Phase 5 — The reviewed item: `DispatchOptions` (needs human-review gate)

`DispatchOptions` — `pipelex/temporal/config_temporal.py` (~line 366) → **frozen `BaseModel`** with `model_config = ConfigDict(arbitrary_types_allowed=True)`. Off-wire (built only inside `WorkerConfig.resolve_dispatch`, immediately consumed by splatting `to_execute_kwargs()` into `workflow.execute_activity(...)`; never a workflow/activity arg/return, never a wire field). Holds a live `temporalio` `RetryPolicy` (non-JSON, `TYPE_CHECKING` forward ref) + the `to_execute_kwargs()` behavior method → `arbitrary_types_allowed` required, `frozen` matches the build-once-read-only lifecycle. NamedTuple/pydantic dataclass are wrong (the method + arbitrary SDK field; and a pydantic dataclass hits the SAME class-def-time annotation-resolution risk as BaseModel — Phase 0 does not change this).

**Load-bearing invariant (the gate):** the module must import without `temporalio` installed. `temporalio` is imported only under `TYPE_CHECKING` and lazily inside `make_retry_policy`; `retry_policy: "RetryPolicy"` is a forward ref. A pydantic model builds a validator at class-def time and may try to resolve that annotation, risking pulling `temporalio` into the plain import path.

- [x] **5.1** GATE: verify the `temporalio`-not-installed import path — run `make tb` on an environment WITHOUT the temporal extra and confirm import + config-load succeed. Keep `RetryPolicy` under `TYPE_CHECKING` (or typed `Any`).
  - Result: **this worktree HAS the temporal extra**, so `make tb` here can't exercise the no-extra path (the prior session flagged exactly this). Used a **subprocess import-block** instead (a `sys.meta_path` finder that raises `ModuleNotFoundError` for `temporalio*`), then imported `config_temporal` and built `DispatchOptions` + the `Temporal` config submodels in that blocked interpreter — all green. **Key finding (the gate's real risk, now characterized):** a bare forward ref `retry_policy: "RetryPolicy"` (TYPE_CHECKING-only, no runtime binding) IMPORTS fine (pydantic *defers* the unresolved schema) but raises `PydanticUserError` the moment a `DispatchOptions` is **constructed** without the extra. Mitigation: an `else: RetryPolicy = Any` branch on the `TYPE_CHECKING` guard binds the annotation to `Any` at runtime, so the field needs no resolution and no `temporalio` — type-checkers still see the real `RetryPolicy`. Locked with a NEW permanent regression test `tests/unit/pipelex/temporal/test_dispatch_options_no_temporalio.py` (subprocess, temporalio blocked) — complements the existing AST scan in `test_config_temporal_optional_dep.py`, which would NOT catch a revert to a bare forward ref (it adds no import statement).
- [x] **5.2** Convert `DispatchOptions` to frozen `BaseModel(arbitrary_types_allowed=True)`, preserving `to_execute_kwargs()`. If the import-clean path proves infeasible, FALL BACK to a NamedTuple with `timedelta | None` fields + the `to_execute_kwargs` method (still off-wire-legal) — record the decision in the Session log.
  - Result: converted to a **frozen pydantic dataclass** (`@pydantic.dataclasses.dataclass(frozen=True)`), `to_execute_kwargs()` + field order unchanged, dropped `from dataclasses import dataclass` → `from pydantic.dataclasses import dataclass`. **DEVIATION 1 — `arbitrary_types_allowed` NOT needed (plan wording superseded):** with the `else: RetryPolicy = Any` binding the `retry_policy` field resolves to `Any` at runtime (no `isinstance`/arbitrary-type handling), so `frozen=True` alone suffices — `arbitrary_types_allowed=True` would be dead config. **DEVIATION 2 — final form is a frozen pydantic dataclass, NOT the plan's frozen `BaseModel`:** this went through TWO gate passes. (a) I first recommended pydantic dataclass; at the review gate the **user initially chose frozen `BaseModel`**, which I implemented (agent-check + full suite green on that form). (b) The user then observed the deciding point: **a frozen `BaseModel` needs the SAME `else: RetryPolicy = Any` binding** (both forms build a validator at class-def time), so BaseModel buys nothing on the import axis — and once the `else:` cost is unavoidable, the lower-churn pydantic dataclass (keep the decorator, no base-class change, no `model_config`) is the net win, and it fits the form guide's off-wire/never-serialized criterion exactly. **Switched to frozen pydantic dataclass.** Empirically reconfirmed import + construct under blocked `temporalio` (`is_pydantic_dataclass(DispatchOptions) == True`; frozen enforced via `FrozenInstanceError`). No NamedTuple fallback — the import-clean path is fully feasible. Behavior preserved: `test_resolve_dispatch.py` still builds real `RetryPolicy` objects and reads `.non_retryable_error_types` off them (14 targeted tests green incl. the new no-temporalio + AST optional-dep tests).

**Verify:** `make agent-check`; `make tb`; `.venv/bin/pytest tests/integration/pipelex/temporal/`.

---

## Phase 6 — Final gate

(Perf-diff steps removed — the harness was dropped in Phase 1; the `DispatchOptions` form decision rests on reasoning, not measurement.)

- [x] **6.1** Final gate: **no stdlib `@dataclass` decorator** — `grep -rn "from dataclasses import" pipelex/ | grep -w dataclass` returns nothing (currently flags only `config_temporal.py`, cleared by Phase 5). **NOTE:** plain `from dataclasses import field` is ALLOWED and expected — the pydantic dataclasses (`error_pages_generator.py`, `jinja2_required_variables.py`) use `dataclasses.field(default_factory=...)` for their defaults; that helper is not a stdlib `@dataclass`, so do NOT grep for the bare `"from dataclasses import"` string (it false-positives on `field`). Then: full `make agent-check` · full `.venv/bin/pytest tests/integration/pipelex/temporal/` · `make agent-test`.
  - Result: `grep -rn "from dataclasses import" pipelex/ | grep -w dataclass` → **NONE** (HARD RULE 1 satisfied). Only `from dataclasses import field` remains (in `jinja2_required_variables.py` + `error_pages_generator.py`, the Phase 3 pydantic dataclasses) — allowed. `make agent-check` clean (ruff + plxt pass, **pyright 0/0**, **mypy 1930 files Success**) · `make tb` 2 passed · `tests/unit/pipelex/temporal/` + `tests/integration/pipelex/temporal/` → **419 passed, 4 xpassed** (the documented pre-existing pytest-xdist class-registration race flakes; pass in isolation), no stray temporal processes · **`make agent-test` full suite green (exit 0)**.
- [x] **6.2** Record the release-time follow-up (still pending): publish new kajson to PyPI + bump the `kajson==` pin in `pipelex/pyproject.toml`.
  - Result: **recorded, still pending (not dev-blocking).** kajson is bumped to `0.6.0` on its `feature/Support-more-types` branch and consumed editable from `../kajson` (live source serves the venv; installed metadata stays `0.5.0`, so the pipelex `kajson==0.5.0` pin holds). Release gate = publish kajson `0.6.0` to PyPI **then** bump the `kajson==` pin in `pipelex/pyproject.toml` to match, before pipelex ships a release that depends on the new pydantic-dataclass wire support. **Do NOT run `uv lock`/`uv sync` in this worktree until that pin bump** — the editable `0.6.0` would conflict with the `==0.5.0` pin.

> 🛑 **HARD STOP 3 — Done.** Converter + kajson generalized (wire rule now BaseModel-or-pydantic-dataclass), all stdlib dataclasses removed, NamedTuple upgrades landed, temporal suite green, denylist types never converted away from BaseModel. Run the context-save protocol; final Session log entry records the Phase 0 test results, the `DispatchOptions` import-invariant outcome, and the pending release-gate.

---

## Leave-as-is (do NOT convert) — confirmed correct already

- `_ThinkingParams` — `pipelex/plugins/anthropic/anthropic_llm_worker.py` — a legitimate pydantic dataclass; off-wire, built+consumed within a single `_gen_text` call. Right tool already. (No longer the *only* pydantic dataclass — `ErrorPagesReport` (3.2), `VariableReference` (3.4), and `DispatchOptions` (5.2) joined it.)
- `ResultFile` (`pipelex/pipe_run/delivery_executor.py`), `SupportCheck` (`pipelex/cogt/img_gen/img_gen_param_support.py`), `StoredData` (`pipelex/tools/storage/storage_provider_abstract.py`), `PipeJobComponents` (`pipelex/pipe_run/pipe_job_factory.py`) — existing off-wire NamedTuples, all correct. (`PipeJobComponents` is a local unpack container for building `PipeJob`; anything embedded INTO `PipeJob` must still be wire-legal.)
- `iter_model_fields` (`pipelex/tools/misc/model_utils.py`, `pipelex/tools/typing/field_helpers.py`) and `items` (`pipelex/tools/misc/func_registry.py`) — keep as plain `Iterator[Tuple[...]]` (`dict.items()` convention). Best follow-up (separate refactor) is consolidating the two duplicate `iter_model_fields`, not changing their data form.
- `generate_from_structure_blueprint` (`pipelex/core/concepts/structure_generation/generator.py` ~line 78) — `(class_code, generated_class)`; one element is a live `type`. Firmly off-wire (a `type` can't round-trip the converter). NamedTuple would be harmless polish but optional — leave unless doing a broader codegen cleanup.

## Rejected — stale candidates that do NOT exist (do not re-propose)

Verified absent by full-tree grep + directory listing. Listed so a future session doesn't re-derive them: `pipelex/cli/run_helpers.py` (`execute_method_and_output`, `_resolve_inputs_and_memory`); `pipelex/cli/ui_helpers.py` (`prompt_for_methods_and_output`); `pipelex/cli/blueprint_writer.py` (the four `_write_*_stub_file`); the entire `pipelex/pipe_operators/ocr/` path; `pipe_func._resolve_content_generator_and_func_name`; `pipe_img_gen_factory._resolve_blueprint_and_factory`; `pipe_llm_blueprint._split_prompt_template`; `pipe_llm_factory._resolve_prompt_template_and_target`; `toml_utils.load_toml_from_path_and_get_content`; `template_provider_abstract._provide_template_text_and_source`; `file_utils._split_filepath_into_components(_with_extension)`; `hub.get_pipelex_hub_and_pipe_router`; `sub_pipe._resolve_condition_expression`; `library_manager.get_library_paths`; `concept_native.NativeConceptClassNamePair`; `concept_factory._parse_concept_string`; `stuff_factory.make_from_str` (returns a single `Stuff`, misdescribed); the removed `pipelex/cocktail/` directory (`_detect_action_type_and_agent`, `_parse_command_line`). The nearest real shape to the gone `blueprint_writer` is `structures_cmd._generate_structures_for_inline` returning `list[tuple[str, str]]` — a weak list-element case, separately scoped; do not fold the non-existent functions into it.

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

### 2026-05-29 — Phase 5 (`DispatchOptions`) + Phase 6 final gate complete — 🛑 HARD STOP 3 reached (refactor DONE)
- Landed: **5.1, 5.2, 6.1, 6.2** flipped with per-item results above. HARD RULE 1 fully satisfied — **zero stdlib `@dataclass` decorators remain in `pipelex/`**. Files touched this session:
  - `pipelex/temporal/config_temporal.py` — `DispatchOptions` `@dataclass` → **frozen pydantic dataclass** (`@pydantic.dataclasses.dataclass(frozen=True)`); added `else: RetryPolicy = Any` runtime binding on the `TYPE_CHECKING` guard; swapped `from dataclasses import dataclass` → `from pydantic.dataclasses import dataclass`.
  - `tests/unit/pipelex/temporal/test_dispatch_options_no_temporalio.py` — **NEW** runtime regression test (subprocess with `temporalio` blocked → import + construct `DispatchOptions`).
  - `TODOS.md` — this update.
- Decisions / deviations:
  - **Form decision: frozen pydantic dataclass, settled over two gate passes.** (a) I recommended a frozen pydantic dataclass (lowest churn from the stdlib `@dataclass`; matches the form guide rewritten last session; the plan's BaseModel-over-pydantic-dataclass reasons don't hold — identical import risk, methods fine on pydantic dataclasses). At the review gate the **user first chose frozen `BaseModel`**, which I implemented and verified (agent-check + full suite green). (b) The user then nailed the deciding point: **a frozen `BaseModel` needs the SAME `else: RetryPolicy = Any` binding**, so it has no import-axis advantage — and with the `else:` cost unavoidable, the lower-churn pydantic dataclass is the net win. **Switched to frozen pydantic dataclass** and re-verified end-to-end. Lesson for the form guide: when an arbitrary-SDK field forces an `else: Any` binding regardless, that cost is NOT a reason to prefer BaseModel — churn + the never-serialized criterion decide, both favoring the pydantic dataclass.
  - **`arbitrary_types_allowed` proved unnecessary** (plan said `BaseModel(arbitrary_types_allowed=True)`). With `else: RetryPolicy = Any`, the `retry_policy` field resolves to `Any` at runtime → no arbitrary-type handling needed; `@dataclass(frozen=True)` alone. Adding `arbitrary_types_allowed` would be dead config, so it was omitted.
  - **The real import invariant, characterized:** a bare forward ref imports (pydantic defers the schema) but raises `PydanticUserError` on *construction* without the extra. `DispatchOptions` is only ever constructed inside `resolve_dispatch` (which already requires `temporalio`), so even a bare ref wouldn't break a real no-extra deployment — but the `else: Any` binding makes import+construct robust regardless, and the new subprocess test locks it.
  - **No fallback to NamedTuple** — the import-clean frozen-BaseModel path is fully feasible (proven by the subprocess gate), so 5.2's fallback clause didn't fire.
  - **Inline-LSP noise reconfirmed:** during editing the inline pyright emitted `temporalio.* could not be resolved` on `config_temporal.py` + a STALE `"dataclass" is not defined` at a pre-edit line number. Authoritative `make agent-check` pyright = **0 errors**; grep confirmed zero `@dataclass`. Trust `make agent-check`, not the inline stream (as the prior sessions noted).
- Verification (all green): `make agent-check` (ruff+plxt clean, pyright 0/0, mypy 1930 files) · `make tb` 2 passed · temporal unit+integration 419 passed / 4 pre-existing xdist xpass / no stray procs · targeted 14-test slice (new no-temporalio + AST optional-dep + resolve_dispatch) green · **`make agent-test` full suite exit 0**.
- Open questions / carry-forward: **the deferred release gate (6.2) is the only thing left** — publish kajson `0.6.0` to PyPI + bump the `kajson==` pin in `pipelex/pyproject.toml`; until then do NOT run `uv lock`/`uv sync` in this worktree (editable `0.6.0` vs `==0.5.0` pin conflict). This is a release-time action, not part of the refactor.
- Code state: **COMMITTED + PUSHED** — commit `326d3232` on `refactor/Dataclasses` (tracks `origin/refactor/Dataclasses`), working tree clean. 3 files: `pipelex/temporal/config_temporal.py`, new `tests/unit/pipelex/temporal/test_dispatch_options_no_temporalio.py`, + this `TODOS.md`. `uv.lock` untouched. A post-implementation code-review pass (self + independent reviewer) fixed two doc-accuracy issues before the commit: the new test's stale "frozen Pydantic `BaseModel`" docstring → "frozen Pydantic dataclass", and trimmed the `DispatchOptions` docstring's BaseModel-vs-dataclass rationale (it lives here in the ledger, not in code). (This `TODOS.md` cold-start update lands as a small follow-up commit after `326d3232`.)
- NEXT ACTION: HARD STOP 3 — the data-class refactor is **DONE** (converter + kajson generalized, all stdlib dataclasses removed, NamedTuple upgrades + per-site forms landed, full suite green). The only remaining item is the release-time kajson PyPI publish + pin bump (6.2), to be done when pipelex cuts a release depending on the new wire support — not a dev task. END THE SESSION.

### 2026-05-29 — Phases 1–4 complete (NamedTuple upgrades + off-wire stdlib removals; perf harness built then dropped) — 🛑 HARD STOP 2 reached
- **POST-REVIEW ADJUSTMENTS (same session, after the user reviewed the work):** (1) **Perf harness DROPPED** — `tests/perf/` deleted entirely. It measured nothing realistic (synthetic stand-ins; the wire-anchor never used the real kajson converter path; costs negligible vs network-bound activities; nothing on a hot path). Phase 1 & Phase 6's perf-diff are struck; the `DispatchOptions` form decision now rests on reasoning. (2) **4.1 `RegistrationFailure` switched NamedTuple → frozen `BaseModel`** — a NamedTuple IS a tuple, which collides with the `tuple[str, ...]` success arm of its union return; a BaseModel stays type-distinct. (3) **2nd review pass — premise update + 3.2/3.4 → pydantic dataclass.** The user clarified the premise: the goal is the *right per-site shape*, and a **pydantic dataclass** (wire-legal since Phase 0) is a first-class off-wire option, often the lowest-churn one. Rewrote the top-of-file form-selection guide accordingly, then converted **3.2 `ErrorPagesReport` → frozen pydantic dataclass** and **3.4 `VariableReference` → non-frozen pydantic dataclass** (both near-zero-diff: keep `field(default_factory=...)` + properties, just swap the decorator import). Kept 3.1 NamedTuple (Protocol field), 3.3 BaseModel (uniform builder layer), 4.1 BaseModel (type-distinct from tuple). agent-check clean (pyright 0/0, mypy 1929); errors+jinja2+templating 318 passed; temporal + setup-namespace 452 passed/4 pre-existing xpass.
- Landed: **2.1, 2.2, 3.1, 3.2, 3.3, 3.4, 4.1** flipped with per-item results above. **1.1/1.2 built-then-dropped** (see above). **2.3 and 2.4 skipped — target code no longer exists in the current tree** (see deviations). Files touched (final state):
  - **Phase 2 (NamedTuple):** `pipelex/core/concepts/concept_factory.py` (+`StructureNameAndRefine`), `pipelex/core/qualified_ref.py` (+`CrossPackageRef`).
  - **Phase 3 (off-wire stdlib removals):** `pipelex/reporting/reporting_manager.py` (`_EventLogContext`→NamedTuple), `pipelex/errors/error_pages_generator.py` (`ErrorPagesReport`→frozen BaseModel), `pipelex/builder/runner_code.py` (`CustomClassInfo`→frozen BaseModel), `pipelex/tools/jinja2/jinja2_required_variables.py` (`VariableReference`→mutable BaseModel).
  - **Phase 4 (temporal-adjacent):** `pipelex/temporal/tprl/namespace_check.py` (`RegistrationFailure`→**frozen BaseModel**, post-review).
  - **Final per-site forms:** 3.1 `_EventLogContext`→NamedTuple · 3.2 `ErrorPagesReport`→**frozen pydantic dataclass** · 3.3 `CustomClassInfo`→frozen BaseModel · 3.4 `VariableReference`→**pydantic dataclass** · 4.1 `RegistrationFailure`→frozen BaseModel · 2.1/2.2→NamedTuple.
- Decisions / deviations:
  - **2.3 / 2.4 do not exist (the audit was stale — taken against the sibling `refactor/Paths` worktree).** `runtime_manager.py` is gone; runtime mode is now property-based in `pipelex/system/runtime.py`. `config_manager.py` is now `pipelex/system/configuration/config_loader.py` and its `find_project_root() -> Path | None` already dropped the `found_root_marker` bool. Both grep-confirmed absent — nothing to convert, so both checkboxes are marked done-by-absence (struck through inline).
  - **3.2 `ErrorPagesReport` — plan rationale was stale; final form is frozen pydantic dataclass.** Plan said "single full-kwargs construction, no in-place `.append`"; actually it's built empty and `.append`-ed in place. `frozen=True` blocks attribute *reassignment*, not list mutation, under stdlib-dataclass / pydantic-dataclass / BaseModel alike — so all three are behavior-equivalent for the append pattern. Final choice (2nd review pass): frozen **pydantic dataclass** — lowest churn (kept `field(default_factory=list[Path])`) and no model-API need.
  - **4.1 `RegistrationFailure` implementer-note verified, not assumed:** re-grepped all consumers; every discrimination is `isinstance(x, RegistrationFailure)`, none is `isinstance(x, tuple)`; success path returns plain tuples (never NamedTuple-subclass instances) so discrimination stays exact.
  - **Only ONE stdlib dataclass remains in `pipelex/`:** `pipelex/temporal/config_temporal.py` (`DispatchOptions`, Phase 5) — grep-confirmed. HARD RULE 1 is one conversion away from satisfied.
  - **Inline LSP noise (informational):** throughout, the editor's inline pyright kept emitting `temporalio.*` "could not be resolved" / "type unknown" diagnostics on temporal files I touched (and the Phase 0 files). That inline checker lacks the temporal extra; the authoritative `make agent-check` pyright resolves `temporalio` and reports **0 errors**. One round of jinja2 diagnostics was also stale (referenced pre-edit line numbers) — verified the file by re-reading; conversion was correct. Trust `make agent-check`, not the inline stream.
- Verification (all green): `make agent-check` clean (ruff+plxt, pyright 0/0, mypy 1932 files) · `make tb` 2 passed · core+pipes 1323 passed/1 xfailed (pre-existing) · temporal unit+integration 445 passed/4 xpassed (pre-existing xdist flakes, no stray procs) · builder+tools+errors+reporting 1676 passed/1 pre-existing skip.
- Open questions / carry-forward: (1) **deferred release gate still pending** — publish new kajson `0.6.0` to PyPI + bump `kajson==` pin in `pipelex/pyproject.toml`; do NOT run `uv lock`/`uv sync` in this worktree until then (editable `0.6.0` vs `==0.5.0` pin would conflict). (2) Phase 5 gate 5.1 wants `make tb` on an env WITHOUT the temporal extra — but THIS worktree HAS temporalio installed, so the next session must arrange a no-temporal-extra import check (separate venv, or a targeted import-isolation test) rather than assuming the local env exercises that path.
- Code state: **COMMITTED + PUSHED** — commit `72e1800f` on `refactor/Dataclasses` (tracks `origin/refactor/Dataclasses`), working tree clean. 8 files: `pipelex/core/concepts/concept_factory.py`, `pipelex/core/qualified_ref.py`, `pipelex/reporting/reporting_manager.py`, `pipelex/errors/error_pages_generator.py`, `pipelex/builder/runner_code.py`, `pipelex/tools/jinja2/jinja2_required_variables.py`, `pipelex/temporal/tprl/namespace_check.py`, + this `TODOS.md`. No new files (the `tests/perf/` harness was created then deleted in the same session). `uv.lock` untouched. (This `TODOS.md` cold-start update lands as a small follow-up commit after `72e1800f`.)
- NEXT ACTION: HARD STOP 2 — END THE SESSION. A fresh session starts **Phase 5** — convert `DispatchOptions` in `pipelex/temporal/config_temporal.py` to frozen `BaseModel(arbitrary_types_allowed=True)`. **Do gate 5.1 FIRST:** confirm the module still imports without the `temporalio` extra (RetryPolicy stays under `TYPE_CHECKING`/typed `Any`); this worktree has temporalio installed, so arrange a no-extra import check. If the import-clean path proves infeasible, fall back to the NamedTuple form (5.2) and record it.

### 2026-05-29 — Phase 0 complete (converter + kajson generalized) — 🛑 HARD STOP 1 reached
- Landed: Pre-flight (both boxes) + **0.1–0.9** all flipped with per-item results above. Two-repo change:
  - **kajson** (`../kajson`, branch `feature/Support-more-types`): `json_decoder.py` gained an explicit `is_pydantic_dataclass` decode branch (validates via the dataclass, raises `KajsonDecoderError` loudly instead of silently returning a raw dict); new `tests/unit/test_pydantic_dataclass.py`; version `0.5.0`→`0.6.0` + CHANGELOG entry.
  - **pipelex** (`_data` worktree): `pipelex/temporal/temporal_data_converter.py` widened — `_is_kajson_wire_value` (to_payload, BaseModel-short-circuit first) and `_is_kajson_type` (from_payload scalar/Optional/list) now also accept pydantic dataclasses; BaseModel path byte-identical. New tests: `data_converter/test_data_conv_dataclass.py` (direct converter + byte-identical regression guard) and `test_wf_dataclass_roundtrip.py` (in-process-server round-trip).
- Decisions / deviations:
  - **kajson test isolation (fixed at root after code review):** `test_json_encoder` / `test_json_decoder` autouse fixtures used to `clear_*coders()` on teardown without restoring, wiping kajson's import-time default codecs process-wide. Now they snapshot the registry and restore it on teardown. An initial band-aid (re-registering `timedelta` in the new dataclass test) was removed.
  - **pyright-strict refactor:** replacing the original inline `isinstance` narrowing with non-narrowing bool predicates surfaced `reportUnknownArgumentType` errors (`type(Any)` → `type[Unknown]`). Resolved cleanly: value predicate param typed `object`, list-head probe extracted to an `object`-typed helper, call sites keep `value` explicitly `Any`, and one `cast("Any", type_hint)` collapses the post-`isinstance` union. No `# pyright: ignore` added in the converter.
  - **Version/pin tension (IMPORTANT for next session):** kajson is bumped to `0.6.0` but pipelex still pins `kajson==0.5.0` (editable source serves live code; installed metadata stays `0.5.0`, so the pin holds and the `.venv` works). Running `uv lock`/`uv sync` here would now FAIL (editable `0.6.0` vs `==0.5.0`). The pin bump + PyPI publish remain the deferred release gate.
- Verification (all green): kajson suite 257 passed / 1 skipped + kajson `make agent-check` clean · pipelex `make agent-check` (pyright 0/0, mypy 1929 files) · `make tb` 2 passed · converter+integration round-trips 11 passed · full temporal integration (non-inference) 136 passed, 4 pre-existing xdist-race xpass, no regressions, no stray temporal processes.
- Open questions: none blocking Phase 1. The only live item is the deferred kajson PyPI publish + `kajson==` pin bump (release gate, not dev-blocking).
- Code state: **uncommitted** (per instruction — not committing without explicit ask). Dirty: kajson = `CHANGELOG.md`, `kajson/json_decoder.py`, `pyproject.toml`, new `tests/unit/test_pydantic_dataclass.py`, plus the code-review root-cause fix in `tests/unit/test_json_encoder.py` + `tests/unit/test_json_decoder.py`; pipelex `_data` = `pipelex/temporal/temporal_data_converter.py`, new `tests/integration/pipelex/temporal/data_converter/test_data_conv_dataclass.py`, new `tests/integration/pipelex/temporal/test_wf_dataclass_roundtrip.py`, and this `TODOS.md`. Tree otherwise clean; `uv.lock` untouched.
- NEXT ACTION: HARD STOP 1 — END THE SESSION. A fresh session starts Phase 1 (perf baseline harness at `tests/perf/test_dataclass_forms_bench.py`, task 1.1), which does not depend on Phase 0 internals. Before any `uv` re-lock, remember the version/pin tension above.

### 2026-05-29 — Ledger created (planning only, no code changes)
- Landed: nothing implemented yet. This ledger was created from the former `wip/data-class-best-practices-plan.md` (removed). The previous root ledger (`feature/API-readiness-4`, all complete) was archived to `wip/error-handling/archive-todos-api-readiness-4.md`.
- Decisions: (1) per-site type strategy for the six stdlib dataclasses — NOT a uniform pydantic-dataclass conversion. (2) Generalize the converter + kajson FIRST as Phase 0, scoped to pydantic dataclasses only. (3) kajson is consumed editable from `../kajson` in this worktree, so no PyPI publish needed for dev; publish + pin bump is a release-time gate.
- Open questions: none blocking. The `DispatchOptions` import-without-temporalio invariant (Phase 5) is the one real unknown — gated by 5.1.
- Code state: clean working tree except this ledger + the archived file move. No production code touched.
- NEXT ACTION: start Phase 0 — Pre-flight boundary freeze, then task 0.1 (kajson `is_pydantic_dataclass` decode branch in `../kajson/kajson/json_decoder.py`), TDD: write the kajson round-trip tests (0.2) first.
