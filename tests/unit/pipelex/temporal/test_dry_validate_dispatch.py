"""Unit tests for ``dispatch_dry_validate`` — the submitter-side round-trip the API route calls.

The helper owns two behavior decisions nothing else pins:

- D-C5 at the workflow tier: ``RetryPolicy(maximum_attempts=1)`` so a deterministically-failed
  validation workflow is never re-run by the server (the config default policy would).
- The interactive execution bound: an explicit ``workflow_execution_timeout`` matching the
  activity retry budget instead of the batch-tuned 1-hour config default, so a worker outage
  fails the HTTP caller fast instead of queueing stale validation work.
"""

from datetime import timedelta

import pytest
from pytest_mock import MockerFixture

from pipelex.temporal.tprl.workflow_caller import WorkflowExecutorFactory
from pipelex.temporal.tprl_pipe.act_dry_validate import DryValidateArg, DryValidateResult
from pipelex.temporal.tprl_pipe.dry_validate_dispatch import dispatch_dry_validate
from pipelex.temporal.tprl_pipe.wf_dry_validate import WfDryValidate


class TestDryValidateDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_pins_no_workflow_retry_and_interactive_timeout(self, mocker: MockerFixture) -> None:
        expected_result = DryValidateResult(dry_run_outputs={}, pending_signatures=[], pipe_structures={})
        fake_executor = mocker.Mock()
        fake_executor.make_workflow_id.return_value = "wf_dry_validate_test"
        fake_executor.execute_workflow = mocker.AsyncMock(return_value=expected_result)
        create_executor = mocker.patch.object(WorkflowExecutorFactory, "create_executor", return_value=fake_executor)

        arg = DryValidateArg(mthds_contents=['domain = "unit_dispatch"'])
        result = await dispatch_dry_validate(arg)

        assert result is expected_result
        create_kwargs = create_executor.call_args.kwargs
        assert create_kwargs["retry_policy"].maximum_attempts == 1
        assert create_kwargs["workflow_execution_timeout"] == timedelta(minutes=12)
        execute_kwargs = fake_executor.execute_workflow.call_args.kwargs
        assert execute_kwargs["workflow_class"] is WfDryValidate
        assert execute_kwargs["workflow_arg"] is arg
        assert execute_kwargs["workflow_id"] == "wf_dry_validate_test"
