from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex.cogt.content_generation.assignment_models import LLMAssignment

with workflow.unsafe.imports_passed_through():
    from typing_extensions import override

    from pipelex.cogt.content_generation.assignment_models import LLMAssignment
    from pipelex.config import get_config
    from pipelex.deep_flow.log_temporal import workflow_log
    from pipelex.deep_flow.tprl.temporal_error import TemporalError
    from pipelex.deep_flow.tprl.workflow_caller import WorkflowClass
    from pipelex.deep_flow.tprl_content_generation.act_llm_generate import act_llm_gen_text


@workflow.defn(name="wf_make_llm_text")
class WfMakeLLMText(WorkflowClass[LLMAssignment, str]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: LLMAssignment,
    ) -> str:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            crafted_text = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_llm_gen_text,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except ActivityError as exc:
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        workflow_log.debug("Workflow complete")
        return crafted_text
