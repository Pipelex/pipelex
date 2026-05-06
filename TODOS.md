# Mistral Workflows ↔ Pipelex Plugin — Plan & Progress

Self-contained planning document. A fresh session can resume from this file
alone; no need to read prior conversation history.

---

## 1. Context

We are integrating Pipelex with Mistral Workflows
(`mistralai-workflows>=3.3.0`), the Mistral orchestration framework that wraps
Temporal with a thicker DX layer. Two goals were considered:

- **Goal 1** — Port Pipelex orchestration to run on Mistral Workflows as an
  alternative durable runtime (replacing/duplicating our existing Temporal
  integration). Outcome: feasible but high friction (3–4 weeks). **Deferred**
  pending answers from the Mistral team about extension hooks for payload
  converter, codec, sandbox, and run_worker. Out of scope for this plan.
- **Goal 2** — Let users invoke Pipelex pipes from inside their own Mistral
  Workflows activities. Low risk, clear user value, ~2 weeks. **In scope.**

This plan covers Goal 2 only. The `mistralai-workflows` dependency must remain
strictly optional.

---

## 2. Background — what we know about Mistral Workflows

Verified by reading the installed package
(`/Users/lchoquel/repos/Pipelex/_mistral/.venv/lib/python3.13/site-packages/mistralai/workflows/`):

- Mistral Workflows IS Temporal underneath. Their `@workflow.define` decorator
  ultimately calls `temporalio.workflow.defn(sandboxed=...)` (see
  `mistralai/workflows/core/workflow.py:170, 251`).
- Their decorator wraps the user's `run` method so the workflow's runtime
  signature becomes `run(self, params: dict | None)`. Caller side dumps params
  via `params.model_dump()` (`core/execution/workflow_execution.py:192-204`).
  This breaks any kajson-based subclass preservation at the workflow boundary
  but **does not affect activities**, whose payload converter handles arg
  serialization directly.
- The Mistral worker hardcodes `MistralWorkflowsPayloadConverter` and
  `MistralWorkflowsPayloadCodec` (`core/worker.py:421-425`). No public override.
- `run_worker(workflows)` connects to the Mistral cloud control plane,
  registers schemas, heartbeats. Requires `MISTRAL_API_KEY`. There is a
  `mistralai.workflows.testing.create_test_worker` for in-process Temporal
  test envs that does NOT require the cloud.
- Activities (`@workflows.activity`) are unrestricted Python — no sandbox,
  no schema constraints beyond JSON-serializable types, no cloud dep at
  invocation time.
- There is a "local execution" mode where `execute_workflow` runs the entry
  method directly without Temporal — only useful for prototyping.
- `OffloadableField` (from `mistralai.extra.workflows`) + an
  `ActivityInOutOffloadingInterceptor` provide automatic large-payload
  offloading at the activity boundary.

Pipelex side (verified by reading the repo):

- `PipeJob` (`pipelex/pipe_run/pipe_job.py:13`) is a BaseModel that already
  has `prepare_for_temporal()` — dehydrates `WorkingMemory` to a raw dict
  when a `LibraryCrate` is present.
- Direct-mode execution: `PipeRun(pipe_router=...)` in
  `pipelex/pipe_run/pipe_run.py:21`. May need a `make_direct_pipe_run()`
  factory if absent — confirm in pre-flight.
- Temporal-mode execution: `make_temporal_pipe_run(...)` in
  `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:104`. Provides `.run()`
  (blocking) and `.start()` (returns `(workflow_id, handle)`).
- `LibraryCrate` already round-trips through Pipelex's own Temporal codec —
  same `model_dump`/`model_validate` will work for our boundary.
- Existing precedent for plugin layout: `pipelex/plugins/mistral/` (the
  Mistral inference plugin). We follow the same shape.
- `pyproject.toml` already declares
  `mistralai-workflows = ["mistralai-workflows>=3.3.0"]` in
  `[project.optional-dependencies]`. No change needed there for Phase 1.

---

## 3. Locked-in design decisions

- [x] **Library crate transport**: dump-based.
      `PipelexPipeRunInput.library_crate_dump: dict[str, Any] | None`. No
      registry-based variant in Phase 1; can be layered in later if asked.
- [x] **Execution mode**: an exhaustive `StrEnum`, set per-call (not
      per-worker). Three modes: `DIRECT`, `TEMPORAL_BLOCKING`,
      `TEMPORAL_FIRE_AND_FORGET`.
- [x] **Streaming**: in-scope, phased — Phase 2.0 ships a single Mistral
      `task()` per activity (started/completed/failed); Phase 2.1 ships
      per-step `task.update()` events driven by Pipelex's `report_delegate`,
      conditional on demand.
- [x] **Plugin location**: `pipelex/plugins/mistralai_workflows/`.
- [x] **Optional-dep guard**: guard lives in `activities.py` (and will live in
      `streaming.py` when added). `__init__.py` is empty per Pipelex's
      "no re-exports" rule. `bridge.py`, `execution_mode.py`, `bootstrap.py`,
      `exceptions.py` are framework-agnostic and importable on a venv that
      does NOT have `mistralai-workflows` installed.
- [x] **Boundary types are JSON-only**. `inputs` and `output_dict` are
      `dict[str, Any]`; `library_crate_dump` is a dict. No Pipelex internal
      types (PipeJob, PipeOutput, WorkingMemory) cross the activity boundary.

---

## 4. Module layout (final)

```
pipelex/plugins/mistralai_workflows/
├── __init__.py                 # optional-dep guard ONLY (no re-exports)
├── exceptions.py               # 4 exception classes
├── execution_mode.py           # PipelexExecutionMode StrEnum
├── bridge.py                   # framework-agnostic core (NO mistralai import)
├── bootstrap.py                # ensure_pipelex_booted() + DI helper
├── activities.py               # @activity-decorated wrappers
└── streaming.py                # Phase 2: mistral task() event forwarding

tests/integration/pipelex/plugins/mistralai_workflows/
├── conftest.py                 # mistralai = pytest.importorskip(...)
├── test_bridge.py              # layer 1: no optional dep needed
├── test_activities_direct.py   # layer 2: needs mistralai-workflows
├── test_activities_temporal_blocking.py   # layer 3: + temporal extra
└── test_activities_streaming.py            # Phase 2
```

Per Pipelex's "no re-exports in `__init__.py`" rule, users import from full
paths:

```python
from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge,
)
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
```

The `__init__.py` exists only to host the import-time guard.

---

## 5. Public API — three usage tiers

### Tier 1 — pre-decorated activity

```python
from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
from pipelex.plugins.mistralai_workflows.bridge import PipelexPipeRunInput
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode

@workflows.workflow.define(name="my-flow")
class MyFlow:
    @workflows.workflow.entrypoint
    async def run(self, doc_url: str) -> dict:
        result = await pipelex_run_pipe(PipelexPipeRunInput(
            pipe_code="extract_invoice",
            inputs={"doc_url": doc_url},
            execution_mode=PipelexExecutionMode.DIRECT,
        ))
        return result.output_dict
```

### Tier 2 — bridge helper inside user's own typed activity

```python
from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput, run_pipe_via_bridge,
)

@workflows.activity(start_to_close_timeout=timedelta(minutes=30), rate_limit=quota)
async def extract_invoice(doc_url: str) -> InvoiceData:
    out = await run_pipe_via_bridge(PipelexPipeRunInput(
        pipe_code="extract_invoice", inputs={"doc_url": doc_url},
    ))
    return InvoiceData.model_validate(out.output_dict)
```

`run_pipe_via_bridge` is the same code the Tier-1 activity calls — just
without the `@activity` decoration. Lets users own per-pipe activity
configuration (timeouts, rate limits, sticky-to-worker, names).

### Tier 3 — full control

Use `build_pipe_job_from_input(...)` and `serialize_pipe_output(...)` from
`bridge.py` directly. For multi-pipe activities, custom delivery, or test
fixtures.

---

## 6. Concrete designs — file by file

### `execution_mode.py`

```python
from pipelex.types import StrEnum

class PipelexExecutionMode(StrEnum):
    """How a Pipelex pipe runs inside a Mistral Workflows activity.

    DIRECT: in-process; no Temporal involved on Pipelex's side; activity
        blocks until the pipe completes. Fastest feedback, simplest ops.
    TEMPORAL_BLOCKING: dispatch the pipe as a Pipelex Temporal workflow;
        the activity awaits completion. Pipe runs durably on Pipelex's
        worker fleet. Requires pipelex[temporal] extra.
    TEMPORAL_FIRE_AND_FORGET: dispatch the pipe as a Pipelex Temporal
        workflow and return immediately with the workflow_id. Activity
        does NOT wait; completion is signalled out-of-band via
        DeliveryAssignment (webhook / storage). Same dep requirements
        as TEMPORAL_BLOCKING. delivery_assignment_dump is required.
    """

    DIRECT = "direct"
    TEMPORAL_BLOCKING = "temporal_blocking"
    TEMPORAL_FIRE_AND_FORGET = "temporal_fire_and_forget"

    @property
    def requires_pipelex_temporal(self) -> bool:
        match self:
            case PipelexExecutionMode.DIRECT:
                return False
            case (
                PipelexExecutionMode.TEMPORAL_BLOCKING
                | PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET
            ):
                return True
```

Exhaustive `match` (no `case _:`) — Pipelex linting requires this and we get
linter errors when a new mode is added.

### `exceptions.py`

```python
from pipelex.exceptions import PipelexError

class MistralWorkflowsPluginError(PipelexError):
    pass

class MistralWorkflowsNotInstalledError(MistralWorkflowsPluginError, ImportError):
    pass

class MissingPipelexTemporalExtraError(MistralWorkflowsPluginError):
    pass

class PipelexBridgeRuntimeError(MistralWorkflowsPluginError):
    pass
```

### `bootstrap.py`

```python
from pathlib import Path
from typing import Callable
from pipelex import Pipelex
from pipelex.system.runtime import RunMode

_BOOTED = False

def ensure_pipelex_booted(
    config_dir: Path | None = None,
    force_run_mode: RunMode | None = None,
) -> None:
    """Idempotent. Boots Pipelex on first call; no-op afterwards."""
    global _BOOTED
    if _BOOTED:
        return
    Pipelex.make(config_dir=config_dir, run_mode=force_run_mode)
    _BOOTED = True

def get_pipelex_dependency() -> Callable[[], Pipelex]:
    """Returns a callable suitable for mistralai.workflows Depends(...)."""
    def _resolver() -> Pipelex:
        ensure_pipelex_booted()
        return Pipelex.get_instance()
    return _resolver
```

User's worker entry-point:

```python
async def main() -> None:
    ensure_pipelex_booted()  # boot once before workers start
    await workflows.run_worker([MyFlow], activities=[pipelex_run_pipe])
```

We don't auto-magic the boot from inside the activity for production
correctness — users should know Pipelex is running. The defensive call
inside `run_pipe_via_bridge` exists only to make first-time-runner mistakes
survivable.

### `bridge.py`

NO `mistralai.workflows` or `temporalio` imports at module top-level.
The Temporal extra is lazy-imported inside the temporal-mode branches.

```python
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
from pipelex.plugins.mistralai_workflows.bootstrap import ensure_pipelex_booted
from pipelex.plugins.mistralai_workflows.exceptions import (
    PipelexBridgeRuntimeError, MissingPipelexTemporalExtraError,
)


class PipelexPipeRunInput(BaseModel):
    """JSON-safe input crossing the Mistral/Temporal boundary."""
    model_config = ConfigDict(extra="forbid")

    pipe_code: str
    domain_code: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_name: str | None = None
    pipeline_run_id: str | None = None  # generated if None
    user_id: str | None = None
    library_crate_dump: dict[str, Any] | None = None
    execution_mode: PipelexExecutionMode = PipelexExecutionMode.DIRECT
    delivery_assignment_dump: dict[str, Any] | None = None


class PipelexPipeRunOutput(BaseModel):
    """JSON-safe output crossing the Mistral/Temporal boundary."""
    model_config = ConfigDict(extra="forbid")

    output_dict: dict[str, Any]
    main_stuff_name: str | None = None
    pipeline_run_id: str
    workflow_id: str | None = None  # set when execution_mode is TEMPORAL_*
    is_completed: bool                # False for FIRE_AND_FORGET
    graph_spec_dump: dict[str, Any] | None = None


def build_pipe_job_from_input(input: PipelexPipeRunInput) -> "PipeJob":
    """Hydrate a PipeJob from JSON-safe input. Loads library_crate if given."""
    ...

def serialize_pipe_output(output: "PipeOutput") -> dict[str, Any]:
    """Dehydrate PipeOutput to JSON-safe dict via dump_for_json/temporal."""
    ...


async def run_pipe_via_bridge(input: PipelexPipeRunInput) -> PipelexPipeRunOutput:
    ensure_pipelex_booted()
    _validate_input(input)
    pipe_job = build_pipe_job_from_input(input)
    delivery = _build_delivery_assignment(input.delivery_assignment_dump)

    match input.execution_mode:
        case PipelexExecutionMode.DIRECT:
            return await _run_direct(pipe_job, delivery)
        case PipelexExecutionMode.TEMPORAL_BLOCKING:
            _require_pipelex_temporal_extra()
            return await _run_temporal_blocking(pipe_job, delivery)
        case PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET:
            _require_pipelex_temporal_extra()
            return await _run_temporal_fire_and_forget(pipe_job, delivery)


def _validate_input(input: PipelexPipeRunInput) -> None:
    if (
        input.execution_mode is PipelexExecutionMode.TEMPORAL_FIRE_AND_FORGET
        and input.delivery_assignment_dump is None
    ):
        msg = (
            "TEMPORAL_FIRE_AND_FORGET requires a delivery_assignment_dump; "
            "otherwise the pipe completion is silently dropped."
        )
        raise PipelexBridgeRuntimeError(msg)


def _require_pipelex_temporal_extra() -> None:
    try:
        import temporalio  # noqa: F401, PLC0415
    except ImportError as exc:
        msg = (
            "TEMPORAL_* execution modes require the pipelex[temporal] extra. "
            "Install with: pip install 'pipelex[temporal,mistralai-workflows]'"
        )
        raise MissingPipelexTemporalExtraError(msg) from exc
```

`_run_direct`, `_run_temporal_blocking`, `_run_temporal_fire_and_forget` are
private helpers; they wrap pipe-run failures into
`PipelexBridgeRuntimeError` (chained from the original exception). No
`except Exception` per Pipelex standards — only catch
`PipeRunError`/`PipeJobError` (and `WorkflowExecutionError` for temporal
modes) explicitly.

### `__init__.py`

```python
from pipelex.plugins.mistralai_workflows.exceptions import (
    MistralWorkflowsNotInstalledError,
)

try:
    import mistralai.workflows  # noqa: F401
except ImportError as exc:
    msg = (
        "The 'mistralai-workflows' optional dependency is not installed. "
        "Install with: pip install 'pipelex[mistralai-workflows]'"
    )
    raise MistralWorkflowsNotInstalledError(msg) from exc
```

Note: `bridge.py`, `execution_mode.py`, `bootstrap.py`, `exceptions.py` can
be imported even when `mistralai-workflows` is NOT installed, because the
guard is in `__init__.py` — but only triggers when the package itself is
imported. To preserve this, **users importing the framework-agnostic
modules must import them via `pipelex.plugins.mistralai_workflows.bridge`
etc., which will run the guard first.** This means the optional dep IS
required even for Tier-3 use. If we want the framework-agnostic core to be
usable without the optional dep, move the guard out of `__init__.py` and
into `activities.py` + `streaming.py` only.

**Decision pending in pre-flight**: should `bridge.py` / `execution_mode.py`
be importable without `mistralai-workflows`? Recommended **yes**, so move
the guard into `activities.py` and `streaming.py` only. (Updated
recommendation overrides §4 / §8 of original design draft.)

### `activities.py`

```python
from datetime import timedelta
from mistralai.workflows import activity  # this triggers ImportError if missing

from pipelex.plugins.mistralai_workflows.bridge import (
    PipelexPipeRunInput, PipelexPipeRunOutput, run_pipe_via_bridge,
)


@activity(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy_max_attempts=3,
)
async def pipelex_run_pipe(input: PipelexPipeRunInput) -> PipelexPipeRunOutput:
    return await run_pipe_via_bridge(input)
```

Future: an `OffloadableField`-using variant for large payloads (Phase 1.5).

---

## 7. Pre-flight verification (before Phase 1.0)

- [x] `PipeOutput` exposes `prepare_for_temporal(library_crate)` that delegates
      to `WorkingMemory.dump_for_temporal()`. We don't need a new
      `dump_for_json()`. The bridge serializes via
      `working_memory.dump_for_temporal()` directly so the output shape is
      consistent regardless of `library_crate`.
- [x] No `make_direct_pipe_run()` factory needed. `PipeRouter()` has no
      required args; the bridge constructs `PipeRun(pipe_router=PipeRouter())`
      inline inside `_run_direct`.
- [x] `LibraryCrate.model_dump()` / `model_validate()` round-trip cleanly
      (verified by `test_bridge_direct.test_direct_mode_with_library_crate_dump`).
- [x] `Pipelex.make()` is **NOT** idempotent — it raises if a singleton
      already exists. `bootstrap.ensure_pipelex_booted()` calls
      `Pipelex.make()` only when `Pipelex.get_optional_instance() is None`,
      which adopts an externally-booted singleton without re-initializing.
- [x] **Guard placement**: chose to put the optional-dep guard in
      `activities.py` only (and in `streaming.py` when added). `__init__.py`
      is empty. `bridge.py`, `execution_mode.py`, `bootstrap.py`, and
      `exceptions.py` are importable without `mistralai-workflows`.
- [x] `DeliveryAssignment.model_dump()` / `model_validate()` round-trip
      cleanly (plain BaseModel; verified in `test_validation`).

---

## 8. Phasing & checklist

### Phase 1.0 — Framework-agnostic core (no optional dep) — **DONE**

Files: `bridge.py`, `execution_mode.py`, `bootstrap.py`, `exceptions.py`.
None of these import `mistralai.workflows` at module top-level. `bridge.py`
lazy-imports `temporalio` only inside the temporal-mode branches.

- [x] Create `pipelex/plugins/mistralai_workflows/` package directory
- [x] Create `__init__.py` (empty — guard lives in `activities.py` only)
- [x] Create `exceptions.py` with all 4 exception classes
      (`MistralWorkflowsPluginError`, `MistralWorkflowsNotInstalledError`,
      `MissingPipelexTemporalExtraError`, `PipelexBridgeRuntimeError`)
- [x] Create `execution_mode.py` with `PipelexExecutionMode` StrEnum and
      `requires_pipelex_temporal` + `is_fire_and_forget` properties using
      exhaustive `match/case`
- [x] Create `bootstrap.py` with `ensure_pipelex_booted()` (idempotent via
      `Pipelex.get_optional_instance()` singleton check — no module-level
      flag needed) and `get_pipelex_dependency()` factory
- [x] Create `bridge.py`:
      - [x] `PipelexPipeRunInput` BaseModel (`extra="forbid"`)
      - [x] `PipelexPipeRunOutput` BaseModel (`extra="forbid"`)
      - [x] `build_pipe_job_from_input(input) -> PipeJob`
      - [x] `serialize_pipe_output(pipe_output) -> dict[str, Any]` —
            always uses `WorkingMemory.dump_for_temporal()` for stable shape
      - [x] `run_pipe_via_bridge(input) -> PipelexPipeRunOutput` with
            exhaustive mode dispatch
      - [x] `_run_direct`, `_run_temporal_blocking`,
            `_run_temporal_fire_and_forget` private helpers
      - [x] `_require_pipelex_temporal_extra()` lazy-import guard
      - [x] `_validate_input()`: FIRE_AND_FORGET + no delivery → raise
      - [x] `_scoped_library_for_crate()` async context manager for per-call
            scoped library when a `library_crate_dump` is provided
- [x] Layer-1 tests — **split across modules** (1 TestClass per module per
      Pipelex pytest standards):
      - [x] `tests/unit/pipelex/plugins/mistralai_workflows/test_input_models.py`
            — input/output BaseModel validation (forbid extra, required
            fields, defaults, JSON round-trip)
      - [x] `tests/unit/pipelex/plugins/mistralai_workflows/test_execution_mode.py`
            — `PipelexExecutionMode` properties
      - [x] `tests/unit/pipelex/plugins/mistralai_workflows/test_validation.py`
            — `_validate_input` (FIRE_AND_FORGET requires delivery),
            `_decode_library_crate` / `_decode_delivery_assignment`
            round-trips, `run_pipe_via_bridge` validation error path
      - [x] `tests/unit/pipelex/plugins/mistralai_workflows/test_dispatch.py`
            — DIRECT / TEMPORAL_BLOCKING / TEMPORAL_FIRE_AND_FORGET dispatch
            with mocked `PipeRun.run` and `make_temporal_pipe_run` (uses
            `PipeJob.model_construct` to bypass Pydantic's pipe validation)
      - [x] `tests/integration/pipelex/plugins/mistralai_workflows/test_bridge_direct.py`
            — DIRECT-mode end-to-end against a real loaded `PipeFunc` test
            pipe; covers globally-loaded library, `library_crate_dump`
            round-trip, and caller-supplied `pipeline_run_id`
- [x] `make agent-check` passes (lint, ruff, pyright, mypy)
- [ ] `make agent-check` passes with `mistralai-workflows` NOT installed
      (not yet verified — needs a fresh venv without the extra)

### Phase 1.1 — Tier 1 activity wrapper — **DONE** (modulo optional pytest marker)

- [x] Create `activities.py` (top-of-file imports `mistralai.workflows` —
      raises `MistralWorkflowsNotInstalledError` with install hint if missing)
- [x] `pipelex_run_pipe` — `@activity(start_to_close_timeout=10min,
      retry_policy_max_attempts=3)`-decorated wrapper around
      `run_pipe_via_bridge`
- [x] Create `tests/integration/pipelex/plugins/mistralai_workflows/conftest.py`
      with the `bridge_test_library` fixture (loads test pipe + registers
      its `mistralai_workflows_bridge_echo` PipeFunc target). The
      `pytest.importorskip("mistralai.workflows")` lives at module-level of
      `test_activities_direct.py` so the rest of the dir (layer-1 bridge
      tests) is NOT skipped when the optional dep is missing.
- [x] Layer-2 integration test (`test_activities_direct.py`):
      - [x] Spin `WorkflowEnvironment.start_local` + `create_test_worker`
      - [x] Define a test workflow that calls `pipelex_run_pipe` in DIRECT
            mode against the registered PipeFunc test pipe
      - [x] Assert `output_dict` shape and `is_completed=True`
- [ ] (Optional) Add `mistralai_workflows` pytest marker to
      `pyproject.toml` markers — **deferred**: the module-level
      `importorskip` already gates the test correctly without a marker.
- [ ] (Optional) Extend `[tool.pytest] addopts` default `-m` filter to
      exclude `mistralai_workflows` — **deferred** for the same reason.

**Issues uncovered + fixed in Phase 1.1**:

1. *Workflow sandbox* rejected pipelex imports during workflow class
   validation. Fixed by wrapping pipelex imports in
   `mistralai_workflows.workflow.unsafe.imports_passed_through()` AND
   passing `enforce_determinism=False` to `@workflow.define` for the test
   workflow.
2. *Search attribute* — Mistral's `@workflow.define` wrapper upserts an
   `OtelTraceId` keyword search attribute on every workflow run. The dev
   server rejects the activation if the attribute isn't pre-registered,
   so the test passes `search_attributes=[SearchAttributeKey.for_keyword(
   "OtelTraceId")]` to `WorkflowEnvironment.start_local`.
3. *Task queue mismatch* — Mistral's `@activity` wrapper dispatches via
   `temporalio.workflow.execute_activity(..., task_queue=
   config.get_effective_task_queue())`, which reads the **global**
   `mistralai_config.temporal.task_queue` (default `"default"`) — NOT the
   workflow's task queue. If we don't override it, activities are
   scheduled on `"default"` while the test worker polls our test queue,
   causing the workflow to hang. Fixed by an autouse module-scoped
   fixture in `test_activities_direct.py` that pins
   `mistralai_config.temporal.task_queue = TEST_TASK_QUEUE` for the
   duration of the module and restores it on teardown.
4. *Result shape* — Mistral's `convert_result_to_temporal_format` wraps
   non-BaseModel returns in `{"result": ...}`. Returning
   `PipelexPipeRunOutput` (a BaseModel) directly from the workflow's
   entrypoint avoids the wrapping — no shape mangling.
5. *mypy* — `mistralai-workflows`'s own source uses PEP 695 type-parameter
   syntax that mypy rejects under `python_version=3.11`. Added a
   `[[tool.mypy.overrides]]` block in `pyproject.toml` with
   `follow_imports = "skip"` and `ignore_errors = true` for
   `mistralai.workflows.*`.

### Phase 1.2 — Temporal modes

- [ ] Wire `_run_temporal_blocking` to call `make_temporal_pipe_run()` and
      await `.run(pipe_job, delivery_assignment)`
- [ ] Wire `_run_temporal_fire_and_forget` to call
      `make_temporal_pipe_run().start(...)`, return immediately with
      `workflow_id` and `is_completed=False`
- [ ] Layer-3 integration test (`test_activities_temporal_blocking.py`):
      - [ ] `pytest.importorskip("temporalio")` at module level
      - [ ] Boot Pipelex with `temporal.is_enabled=true` against the test
            Temporal env
      - [ ] Run a Mistral activity that dispatches a Pipelex `WfPipeRun`
            and blocks on the result
      - [ ] Assert end-to-end output equality with a DIRECT-mode reference
            run of the same pipe
- [ ] Layer-3 fire-and-forget test:
      - [ ] Mock `DeliveryExecutor` / webhook target
      - [ ] Verify activity returns immediately with non-None
            `workflow_id` and `is_completed=False`
      - [ ] Verify the Pipelex workflow eventually completes and posts to
            the delivery target

### Phase 1.3 — Docs, changelog, CI matrix

- [ ] Write `docs/under-the-hood/mistralai-workflows-plugin.md` (overview +
      install + when to use which `PipelexExecutionMode`)
- [ ] Write `docs/under-the-hood/mistralai-workflows-recipes.md` with
      worked examples: Tier 1, Tier 2, library_crate
- [ ] Update `CHANGELOG.md` Unreleased: "Added: Pipelex pipes can now be
      invoked from inside Mistral Workflows activities via the new
      `pipelex.plugins.mistralai_workflows` plugin."
- [ ] CI matrix:
      - [ ] `unit` lane: `pip install -e .[dev]` — runs layer 1
      - [ ] `mistralai-workflows` lane:
            `pip install -e .[dev,mistralai-workflows]` — adds layer 2
      - [ ] `mistralai-workflows-temporal` lane:
            `pip install -e .[dev,mistralai-workflows,temporal]` — adds
            layer 3
- [ ] Add a starter example to `pipelex-cookbook/` under a new
      `mistral-workflows/` directory

### Phase 1.5 — Large payload offloading

- [ ] Add an `OffloadableField`-using variant of `PipelexPipeRunInput` /
      `PipelexPipeRunOutput` in `activities.py` (the import lives behind
      the optional-dep boundary, fine)
- [ ] Wire the variant into a second pre-decorated activity
      `pipelex_run_pipe_offloaded`, OR add a parameter to the existing one
- [ ] Test with a large fixture (>2MB) to confirm offload path works
      end-to-end with Mistral's `ActivityInOutOffloadingInterceptor`
- [ ] Document the trade-off (output stored in Mistral-managed storage)

### Phase 2.0 — Streaming v1 (one task per activity)

- [ ] Create `streaming.py` (imports `mistralai.workflows`)
- [ ] Wrap `pipelex_run_pipe` body in `async with workflows.task(...) as t:`
- [ ] Emit `started` event with `pipe_code` + `pipeline_run_id`
- [ ] Emit `completed` with output summary on success
- [ ] Emit `failed` with exception details on error
- [ ] Layer-4 streaming test using `create_test_worker_with_events` +
      `create_capturing_mock_events_client`

### Phase 2.1 — Streaming v2 (per-step granularity, conditional on demand)

- [ ] Subscribe to `report_delegate` event stream from inside the activity
- [ ] Map Pipelex events to Mistral `task.update(...)` calls:
      - Pipe sub-step started → `in_progress` with description
      - Stuff added to working memory → `in_progress` with new key
      - Pipe step completed → progress %
- [ ] Forwarder side-task: drain event log; terminate cleanly when the
      activity returns; cover both success and failure paths
- [ ] Test: assert per-step events emitted in correct order for a
      multi-step pipe

---

## 9. Pyproject.toml changes — actual

**Applied**:

- Added a `[[tool.mypy.overrides]]` block for `mistralai.workflows.*` with
  `follow_imports = "skip"` and `ignore_errors = true` (mistralai's source
  uses PEP 695 type syntax that mypy rejects under `python_version=3.11`).

**Deferred** — the module-level `pytest.importorskip("mistralai.workflows")`
in `test_activities_direct.py` already gates the layer-2 test correctly
without a marker. Reconsider if test runtime grows or other tests need to
opt in/out of the optional dep:

```toml
# tool.pytest markers — not yet added
"mistralai_workflows: tests that require the mistralai-workflows optional dependency",
```

```toml
# tool.pytest addopts default exclusion — not yet extended
"-m", "not (inference or llm or img_gen or extract or search or pipelex_api or mistralai_workflows)",
```

`[project.optional-dependencies].mistralai-workflows` already declared:
`["mistralai-workflows>=3.3.0"]`. No change.

---

## 10. Phase 1 done criteria

- [ ] Plugin module compiles and `make agent-check` passes with
      `mistralai-workflows` installed
- [ ] `make agent-check` passes with `mistralai-workflows` NOT installed
      (no spurious imports)
- [ ] Layer-1 tests pass on a no-extras venv
- [ ] Layer-2 tests pass on `[dev,mistralai-workflows]` (DIRECT mode e2e)
- [ ] Layer-3 tests pass on `[dev,mistralai-workflows,temporal]`
      (TEMPORAL_BLOCKING + FIRE_AND_FORGET)
- [ ] `pipelex_run_pipe` round-trips a pipe with dynamic-concept output
      via `library_crate_dump`
- [ ] Documentation published; CHANGELOG entry merged
- [ ] Cookbook example added

---

## 11. Risks / open items (track but don't block)

- [ ] FIRE_AND_FORGET footgun mitigation — validation in
      `run_pipe_via_bridge` before mode dispatch (covered in design)
- [ ] Pipelex bootstrap inside an already-bootstrapped Mistral worker —
      confirm singleton guard is reentrant (pre-flight)
- [ ] Concurrent activities sharing process-global Pipelex state — reuse
      per-call library scoping from
      `pipelex/temporal/tprl_pipe/wf_pipe_router.py`; verify no leakage
      under concurrent activity load
- [ ] Mistral's payload converter calls `params.model_dump()` at the
      *workflow* call site only; activities use the converter directly.
      Our boundary is JSON-only, so no kajson preservation needed —
      confirm by integration test with a pipe that produces a
      dynamic-concept output
- [ ] If Mistral upgrades break our use of `OffloadableField` location,
      revisit (currently `mistralai.extra.workflows`)
- [ ] **Goal 1 deferred**: porting Pipelex orchestration to Mistral
      Workflows as an alternative durable runtime is blocked on Mistral
      adding extension hooks for payload converter, codec, sandbox
      passthrough, and a bare-Temporal `run_worker` mode. File issues
      with the Mistral team if/when we want to revisit.

---

## 12. Resuming a session

1. Read this file end-to-end.
2. Find the first unchecked box. If it's in §7 (pre-flight), resolve those
   first — they may change the design (e.g. guard placement decision).
3. Implement the next phase's items in order, checking off boxes as you go.
4. Update §3 (locked-in decisions) only when an explicit user decision
   changes the design; otherwise the design in §4–§6 is authoritative.
5. After each phase, run `make agent-check` and `make agent-test` (with
   the appropriate extras installed for the phase) before moving on.
