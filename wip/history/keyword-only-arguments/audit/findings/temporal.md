# Suspects — package `temporal`

Reviewed: 39 Section A + 13 primitive lone-subjects. Suspects: 5.

## High confidence

- `pipelex/temporal/task_manager.py:36` — `TaskManager.run_worker` — `async def run_worker(self, is_not_sandboxed: bool, *, is_unit_testing: bool, ...)` — `is_not_sandboxed` is a boolean flag that reads opaquely positionally: `run_worker(True)` reveals nothing. It's not the semantic object the method acts on; the worker it launches is. Both real call sites already pass it as `is_not_sandboxed=...`. The `temporal_task_manager.py` override (which carries `@override` and is thus skip-exempt) would track automatically once the Protocol base is fixed. Suggested fix: make the signature fully keyword-only — `async def run_worker(self, *, is_not_sandboxed: bool, is_unit_testing: bool, ...)`.

- `pipelex/temporal/tprl/workflow_caller.py:298` — `WorkflowExecutorFactory.create_executor` — `def create_executor(cls, task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — `task_queue` is one of many configuration options for the executor being created; `create_executor` doesn't designate it as the subject (no "for this queue" or "on this queue" semantic). All four existing call sites pass it as `task_queue=...`. Suggested fix: move `task_queue` after `*` — `def create_executor(cls, *, task_queue: str | None = None, workflow_execution_timeout, ...)`.

- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:127` — `make_temporal_pipe_router` — `def make_temporal_pipe_router(task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — same pattern as `create_executor`: `task_queue` is a configuration option defaulting to `None`, not the semantic object of a "make router" call. Suggested fix: `def make_temporal_pipe_router(*, task_queue: str | None = None, workflow_execution_timeout, ...)`.

- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:131` — `make_temporal_pipe_run` — `def make_temporal_pipe_run(task_queue: str | None = None, *, workflow_execution_timeout, retry_policy, ...)` — same pattern as `make_temporal_pipe_router`. Suggested fix: `def make_temporal_pipe_run(*, task_queue: str | None = None, workflow_execution_timeout, ...)`.

## Medium / low confidence

- `pipelex/temporal/worker_cli.py:25` — `run_worker` — `async def run_worker(project: str | None = None, *, is_not_sandboxed: bool, is_unit_testing: bool, ...)` — `project` defaults to `None` and is looked up from pyproject.toml when absent. Its role is closer to a context/config override than the semantic subject of "run a worker". The one real call site passes it positionally (`run_worker(project, is_not_sandboxed=...)`) from the Typer command, but a fully keyword-only form would be equally natural. Medium confidence — `project` does describe which project's worker to run, so the positional reading is defensible.
