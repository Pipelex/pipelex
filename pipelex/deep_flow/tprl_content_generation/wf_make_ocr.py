from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import OcrAssignment
from pipelex.cogt.ocr.ocr_output import OcrOutput

with workflow.unsafe.imports_passed_through():
    from citadel.config_citadel import get_config
    from deep_flow.log_temporal import workflow_log
    from deep_flow.tprl.temporal_error import TemporalError
    from deep_flow.tprl.workflow_caller import WorkflowClass
    from deep_flow.tprl_content_generation.act_ocr_generate import act_ocr_gen_extract_pages
    from typing_extensions import override

    import pipelex.cogt.content_generation.assignment_models  # noqa: F401
    from pipelex import log
    from pipelex.cogt.content_generation.assignment_models import OcrAssignment
    from pipelex.cogt.ocr.ocr_output import OcrOutput


@workflow.defn(name="wf_make_ocr")
class WfMakeOcr(WorkflowClass[OcrAssignment, OcrOutput]):
    @override
    @workflow.run
    async def run(
        self,
        workflow_arg: OcrAssignment,
    ) -> OcrOutput:
        workflow_log.debug("Workflow start")
        worker_config = get_config().deep_flow.worker_config
        try:
            ocr_output = await workflow.start_activity(  # pyright: ignore[reportUnknownMemberType, reportAssignmentType]
                activity=act_ocr_gen_extract_pages,
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
        return ocr_output
