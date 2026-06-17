"""One-step wrapper workflow dispatching the dry-run+validation activity.

The dispatch unit the API awaits for a Temporal-enabled ``/validate``: it runs the single
``act_dry_validate`` activity and returns its result — functionally identical to a standalone
activity call, but it works on the current ``temporalio`` SDK with no bump (the pre-flight
dispatch decision). Replacing it with a true standalone activity is the deferred Phase-G0
optimization.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_pipe.act_dry_validate import DryValidateArg, DryValidateResult, act_dry_validate


@workflow.defn(name="wf_dry_validate")
class WfDryValidate(WorkflowClass[DryValidateArg, DryValidateResult]):
    """Runs ``act_dry_validate`` once and returns its result."""

    @override
    @workflow.run
    async def run(self, workflow_arg: DryValidateArg) -> DryValidateResult:
        # D-C5: explicit timeout + retry bounds, deterministic in workflow code (no config reads).
        # Validation is deterministic — its failures must NOT retry. The deterministic-failure
        # surface crosses the boundary as TWO types: validate_bundle wraps
        # DryRunError / PipeRunError / PipelexInterpreterError into
        # ValidateBundleError before they escape, and build_pipe_io_contracts wraps a
        # JSON-Schema rendering failure into PipeIOContractError; the activity-boundary
        # TemporalError carries the OUTER PipelexError class name as the ApplicationError
        # type (which is what non_retryable_error_types matches). The graph arm never raises
        # domain errors (it degrades to graph_spec=None). Everything else (worker crash,
        # transient infra) gets one retry.
        return await workflow.execute_activity(
            act_dry_validate,
            arg=workflow_arg,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=2,
                non_retryable_error_types=["ValidateBundleError", "PipeIOContractError"],
            ),
        )
