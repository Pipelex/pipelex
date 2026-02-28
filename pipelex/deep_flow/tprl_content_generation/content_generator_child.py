from typing import Any, cast

from pydantic import BaseModel
from temporalio import workflow
from temporalio.exceptions import ApplicationError, ChildWorkflowError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ImggAssignment,
    Jinja2Assignment,
    LLMAssignment,
    LLMAssignmentFactory,
    ObjectAssignment,
    OcrAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.config import get_config
from pipelex.deep_flow.exceptions import ContentGenerationError
from pipelex.deep_flow.tprl.temporal_error import TemporalError
from pipelex.deep_flow.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from pipelex.deep_flow.tprl_content_generation.content_generator_models import AssignmentType, ResultType
from pipelex.deep_flow.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.deep_flow.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.deep_flow.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.deep_flow.tprl_content_generation.wf_make_object import (
    WfMakeObject,
    WfMakeObjectList,
    WfMakeTextThenObject,
    WfMakeTextThenObjectList,
)
from pipelex.deep_flow.tprl_content_generation.wf_make_ocr import WfMakeOcr
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.exceptions import RootException
from pipelex.tools.runtime_manager import WorkerMode, runtime_manager
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


def make_child_workflow_id(base_id: str) -> str:
    prefix: str
    if worker_mode := runtime_manager.worker_mode:
        match worker_mode:
            case WorkerMode.UNIT_TEST:
                prefix = "utw-"
            case WorkerMode.NORMAL:
                prefix = ""
    else:
        prefix = ""

    info = workflow.info()
    workflow_id = f"{prefix}{info.workflow_id}-{base_id}"
    log.debug(f"Child workflow_id: {workflow_id}")
    return workflow_id


class ContentGeneratorChild(WorkflowExecutor[AssignmentType, ResultType], ContentGeneratorProtocol):
    @override
    @update_job_metadata
    async def make_llm_text(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: str | None = None,
    ) -> str:
        log.debug(f"ContentGeneratorChild make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        try:
            llm_assignment = LLMAssignment(
                job_metadata=job_metadata,
                llm_setting=llm_setting_main,
                llm_prompt=llm_prompt_for_text,
            )
            log.verbose(llm_assignment.desc, title="llm_assignment")

            generated_text = (
                await WorkflowExecutorFactory[LLMAssignment, str]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeLLMText,
                    workflow_arg=llm_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-text"),
                )
            )

        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated text: {generated_text}")
        return generated_text

    @override
    @update_job_metadata
    async def make_object_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        log.verbose(f"ContentGeneratorChild make_object_direct: {llm_prompt_for_object}")
        try:
            llm_assignment_for_object = LLMAssignment(
                job_metadata=job_metadata,
                llm_setting=llm_setting_for_object,
                llm_prompt=llm_prompt_for_object,
            )
            object_assignment = ObjectAssignment.make_for_class(
                object_class=object_class,
                llm_assignment=llm_assignment_for_object,
            )

            obj = (
                await WorkflowExecutorFactory[ObjectAssignment, BaseModel]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeObject,
                    workflow_arg=object_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-object-direct"),
                )
            )
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated object direct: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @update_job_metadata
    async def make_text_then_object(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: LLMPromptFactoryAbstract | None = None,
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        try:
            llm_assignment_for_text = LLMAssignment(
                job_metadata=job_metadata,
                llm_setting=llm_setting_main,
                llm_prompt=llm_prompt_for_text,
            )

            llm_assignment_factory_to_object = LLMAssignmentFactory(
                job_metadata=job_metadata,
                llm_setting=llm_setting_for_object,
                llm_prompt_factory=llm_prompt_factory_for_object or LLMPromptTemplate.for_structure_from_preliminary_text(),
            )
            tto_assignment = TextThenObjectAssignment(
                object_class_name=object_class.__name__,
                llm_assignment_for_text=llm_assignment_for_text,
                llm_assignment_factory_to_object=llm_assignment_factory_to_object,
            )

            obj = (
                await WorkflowExecutorFactory[TextThenObjectAssignment, BaseModel]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeTextThenObject,
                    workflow_arg=tto_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-text-then-object"),
                )
            )
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated object after text: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @update_job_metadata
    async def make_object_list_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )

        obj_list = (
            await WorkflowExecutorFactory[ObjectAssignment, list[BaseModel]]
            .create_executor()
            .execute_child_workflow(
                workflow_class=WfMakeObjectList,
                workflow_arg=object_assignment,
                workflow_id=make_child_workflow_id(base_id=wfid or "craft-object-list-direct"),
            )
        )
        log.verbose(f"ContentGeneratorChild generated object list direct: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

    @override
    @update_job_metadata
    async def make_text_then_object_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: LLMPromptFactoryAbstract | None = None,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        try:
            llm_assignment_for_text = LLMAssignment(
                job_metadata=job_metadata,
                llm_setting=llm_setting_main,
                llm_prompt=llm_prompt_for_text,
            )

            llm_assignment_factory_to_object = LLMAssignmentFactory(
                job_metadata=job_metadata,
                llm_setting=llm_setting_for_object_list,
                llm_prompt_factory=llm_prompt_factory_for_object_list or LLMPromptTemplate.for_structure_from_preliminary_text(),
            )
            tto_assignment = TextThenObjectAssignment(
                object_class_name=object_class.__name__,
                llm_assignment_for_text=llm_assignment_for_text,
                llm_assignment_factory_to_object=llm_assignment_factory_to_object,
            )

            obj_list = (
                await WorkflowExecutorFactory[TextThenObjectAssignment, list[BaseModel]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeTextThenObjectList,
                    workflow_arg=tto_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-text-then-object-list"),
                )
            )
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated object list after text: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

    @override
    @update_job_metadata
    async def make_single_image(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        imgg_job_params: ImggJobParams | None = None,
        imgg_job_config: ImggJobConfig | None = None,
        wfid: str | None = None,
    ) -> GeneratedImage:
        imgg_config = get_config().cogt.imgg_config
        try:
            # We're using workflowWfMakeImages which can generate several images but we're asking for only one
            imgg_assignment = ImggAssignment(
                job_metadata=job_metadata,
                imgg_handle=imgg_handle,
                imgg_prompt=imgg_prompt,
                imgg_job_params=imgg_job_params or imgg_config.make_default_imgg_job_params(),
                imgg_job_config=imgg_job_config or imgg_config.imgg_job_config,
                nb_images=1,
            )

            generated_image_list = (
                await WorkflowExecutorFactory[ImggAssignment, list[GeneratedImage]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeImages,
                    workflow_arg=imgg_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-image"),
                )
            )
            if len(generated_image_list) != 1:
                msg = f"Expected 1 image, got {len(generated_image_list)}"
                raise ContentGenerationError(msg)
            generated_image = generated_image_list[0]
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated image: {generated_image}")
        return generated_image

    @override
    @update_job_metadata
    async def make_image_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        nb_images: int,
        imgg_job_params: ImggJobParams | None = None,
        imgg_job_config: ImggJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[GeneratedImage]:
        imgg_config = get_config().cogt.imgg_config
        try:
            imgg_assignment = ImggAssignment(
                job_metadata=job_metadata,
                imgg_handle=imgg_handle,
                imgg_prompt=imgg_prompt,
                imgg_job_params=imgg_job_params or imgg_config.make_default_imgg_job_params(),
                imgg_job_config=imgg_job_config or imgg_config.imgg_job_config,
                nb_images=nb_images,
            )

            generated_image_list = (
                await WorkflowExecutorFactory[ImggAssignment, list[GeneratedImage]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeImages,
                    workflow_arg=imgg_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-image"),
                )
            )
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated image list: {generated_image_list}")
        return generated_image_list

    @override
    async def make_jinja2_text(
        self,
        context: dict[str, Any],
        jinja2_name: str | None = None,
        jinja2: str | None = None,
        prompting_style: PromptingStyle | None = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
        wfid: str | None = None,
    ) -> str:
        jinja2_assignment = Jinja2Assignment(
            context=context,
            jinja2_name=jinja2_name,
            jinja2=jinja2,
            prompting_style=prompting_style,
            template_category=template_category,
        )
        jinja2_text = (
            await WorkflowExecutorFactory[Jinja2Assignment, str]
            .create_executor()
            .execute_child_workflow(
                workflow_class=WfMakeJinja2Text,
                workflow_arg=jinja2_assignment,
                workflow_id=make_child_workflow_id(base_id=wfid or "jinja2-text"),
            )
        )
        log.verbose(f"ContentGeneratorChild jinja2: {jinja2_text}")
        return jinja2_text

    @override
    async def make_ocr_extract_pages(
        self,
        job_metadata: JobMetadata,
        ocr_input: OcrInput,
        ocr_handle: OcrHandle,
        ocr_job_params: OcrJobParams | None = None,
        ocr_job_config: OcrJobConfig | None = None,
        wfid: str | None = None,
    ) -> OcrOutput:
        try:
            ocr_assignment = OcrAssignment(
                job_metadata=job_metadata,
                ocr_handle=ocr_handle,
                ocr_input=ocr_input,
                ocr_job_params=ocr_job_params or OcrJobParams.make_default_ocr_job_params(),
                ocr_job_config=ocr_job_config or OcrJobConfig(),
            )

            ocr_output = (
                await WorkflowExecutorFactory[OcrAssignment, OcrOutput]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeOcr,
                    workflow_arg=ocr_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "ocr"),
                )
            )
        except RootException as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated ocr output: {ocr_output}")
        return ocr_output
