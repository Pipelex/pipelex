"""Submitter-side dispatch for the dry-run+validation wrapper workflow.

The single round-trip a Temporal-enabled ``/validate`` caller awaits: dispatch
``WfDryValidate`` (which runs the one ``act_dry_validate`` activity in-process on a worker)
and get back the per-pipe status map + the best-effort ``GraphSpec``. Used by the API route
(cross-repo, ``pipelex-api``) and by the Tier-2d e2e submitter script.
"""

from temporalio.common import RetryPolicy

from pipelex.config import get_config
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutorFactory
from pipelex.temporal.tprl_pipe.act_dry_validate import DryValidateArg, DryValidateResult
from pipelex.temporal.tprl_pipe.wf_dry_validate import WfDryValidate


async def dispatch_dry_validate(
    arg: DryValidateArg,
    *,
    task_queue: str | None = None,
    should_auto_connect_temporal: bool = True,
) -> DryValidateResult:
    """Dispatch ``WfDryValidate`` to a worker and await ``{status map, GraphSpec}``.

    A validation failure (strict-mode signature refusal, unexpected pipe failure) comes back
    as ``WorkflowExecutionError`` carrying the structured ``ErrorReport`` recovered by
    ``WorkflowExecutor.execute_workflow`` — the same error shape every other Temporal dispatch
    surfaces, which the API renders as an RFC 7807 422.

    Args:
        arg: The serializable activity input (contents, dirs, uris, allow_signatures, pipe_code).
        task_queue: Optional task-queue override; defaults to the configured default queue.
        should_auto_connect_temporal: Whether the executor may auto-connect the Temporal client.

    Returns:
        The activity result: per-pipe status map + best-effort GraphSpec.
    """
    worker_config = get_config().temporal.worker_config
    executor = WorkflowExecutorFactory[DryValidateArg, DryValidateResult]().create_executor(
        task_queue=task_queue or worker_config.default_task_queue,
        should_auto_connect_temporal=should_auto_connect_temporal,
        # No workflow-level retry (D-C5): validation is deterministic, so re-running the whole
        # wrapper workflow on failure is pure waste — the config default policy would re-run a
        # failed validation up to 3 times (its non_retryable list doesn't know ValidateBundleError).
        # Transient infra failures are already retried at the ACTIVITY tier by WfDryValidate's own
        # bounded policy.
        retry_policy=RetryPolicy(maximum_attempts=1),
    )
    workflow_id = executor.make_workflow_id(pipeline_run_id=f"dry_validate_{PipelineFactory.make_pipeline_run_id()}")
    return await executor.execute_workflow(
        workflow_class=WfDryValidate,
        workflow_arg=arg,
        workflow_id=workflow_id,
    )
