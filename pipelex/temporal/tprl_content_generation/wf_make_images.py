from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError
from typing_extensions import override

with workflow.unsafe.imports_passed_through():
    from pipelex import log
    from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
    from pipelex.config import get_config
    from pipelex.core.stuffs.image_content import ImageContent
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl.temporal_error import TemporalError
    from pipelex.temporal.tprl.workflow_caller import WorkflowClass
    from pipelex.temporal.tprl_content_generation.act_img_gen_generate import act_img_gen_images


@workflow.defn(name="wf_make_image")
class WfMakeImages(WorkflowClass[ImgGenAssignment, list[ImageContent]]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: ImgGenAssignment,
    ) -> list[ImageContent]:
        workflow_log.debug("Workflow start")
        worker_config = get_config().temporal.worker_config
        try:
            image_content_list = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_img_gen_images,
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
        return image_content_list
