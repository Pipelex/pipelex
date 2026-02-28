from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment

with workflow.unsafe.imports_passed_through():
    from typing_extensions import override

    from pipelex.cogt.content_generation.assignment_models import (
        TemplatingAssignment,
    )
    from pipelex.config import get_config
    from pipelex.deep_flow.log_temporal import workflow_log
    from pipelex.deep_flow.tprl.temporal_error import TemporalError
    from pipelex.deep_flow.tprl.workflow_caller import WorkflowClass
    from pipelex.deep_flow.tprl_content_generation.act_jinja2_generate import (
        act_jinja2_gen_text,
    )


@workflow.defn(name="wf_make_jinja2_text")
class WfMakeJinja2Text(WorkflowClass[TemplatingAssignment, str]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: TemplatingAssignment,
    ) -> str:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            jinja2_text: str = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_jinja2_gen_text,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        workflow_log.debug("Workflow complete")
        return jinja2_text
