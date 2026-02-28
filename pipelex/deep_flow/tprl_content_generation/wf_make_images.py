from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import ImggAssignment
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job_components import LLMJobParams

with workflow.unsafe.imports_passed_through():
    from citadel.config_citadel import get_config
    from deep_flow.log_temporal import workflow_log
    from deep_flow.tprl.temporal_error import TemporalError
    from deep_flow.tprl.workflow_caller import WorkflowClass
    from deep_flow.tprl_content_generation.act_imgg_generate import act_imgg_gen_images
    from typing_extensions import override

    import pipelex.cogt.content_generation.assignment_models  # noqa: F401
    import pipelex.cogt.image.prompt_image  # noqa: F401
    import pipelex.cogt.imgg.imgg_job  # noqa: F401
    import pipelex.cogt.imgg.imgg_prompt  # noqa: F401
    import pipelex.cogt.llm.llm_models.llm_deck  # noqa: F401
    import pipelex.cogt.llm.llm_models.llm_setting  # noqa: F401
    import pipelex.cogt.llm.llm_prompt  # noqa: F401
    import pipelex.cogt.llm.llm_prompt_factory_abstract  # noqa: F401
    import pipelex.cogt.llm.llm_prompt_template  # noqa: F401
    from pipelex import log
    from pipelex.cogt.content_generation.assignment_models import ImggAssignment
    from pipelex.cogt.image.prompt_image import (
        PromptImage,  # noqa: F401
        PromptImageBytes,  # noqa: F401
        PromptImagePath,  # noqa: F401
        PromptImageUrl,  # noqa: F401
    )
    from pipelex.cogt.llm.llm_job_components import LLMJobParams  # noqa: F401


@workflow.defn(name="wf_make_image")
class WfMakeImages(WorkflowClass[ImggAssignment, list[GeneratedImage]]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: ImggAssignment,
    ) -> list[GeneratedImage]:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            generated_image_list = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_imgg_gen_images,
                arg=workflow_arg,
                start_to_close_timeout=worker_config.workflow_execution_timeout,
                retry_policy=worker_config.retry_policy,
            )
        except ActivityError as exc:
            log.error(f"ActivityError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise

        workflow_log.debug("Workflow complete")
        return generated_image_list
