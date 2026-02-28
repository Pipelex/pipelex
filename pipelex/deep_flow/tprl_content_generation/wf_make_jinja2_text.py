from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex.cogt.content_generation.assignment_models import Jinja2Assignment, LLMAssignment

with workflow.unsafe.imports_passed_through():
    from citadel.config_citadel import get_config
    from deep_flow.log_temporal import workflow_log
    from deep_flow.tprl.temporal_error import TemporalError
    from deep_flow.tprl.workflow_caller import WorkflowClass
    from deep_flow.tprl_content_generation.act_jinja2_generate import (
        act_jinja2_gen_text,
    )
    from typing_extensions import override

    import pipelex.cogt.content_generation.assignment_models  # noqa: F401
    import pipelex.cogt.llm.llm_models.llm_deck  # noqa: F401
    import pipelex.cogt.llm.llm_models.llm_setting  # noqa: F401
    import pipelex.cogt.llm.llm_prompt  # noqa: F401
    import pipelex.cogt.llm.llm_prompt_factory_abstract  # noqa: F401
    import pipelex.cogt.llm.llm_prompt_template  # noqa: F401
    from pipelex.cogt.content_generation.assignment_models import (
        Jinja2Assignment,
        LLMAssignment,  # noqa: F401
    )


@workflow.defn(name="wf_make_jinja2_text")
class WfMakeJinja2Text(WorkflowClass[Jinja2Assignment, str]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: Jinja2Assignment,
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
