from typing import Any, cast

from pydantic import BaseModel
from temporalio import workflow
from temporalio.exceptions import ApplicationError, ChildWorkflowError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    LLMAssignmentFactory,
    ObjectAssignment,
    TemplatingAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.config import get_config
from pipelex.deep_flow.exceptions import ContentGenerationError
from pipelex.deep_flow.tprl.temporal_error import TemporalError
from pipelex.deep_flow.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from pipelex.deep_flow.tprl_content_generation.content_generator_models import AssignmentType, ResultType
from pipelex.deep_flow.tprl_content_generation.wf_make_extract import WfMakeOcr
from pipelex.deep_flow.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.deep_flow.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.deep_flow.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.deep_flow.tprl_content_generation.wf_make_object import (
    WfMakeObject,
    WfMakeObjectList,
    WfMakeTextThenObject,
    WfMakeTextThenObjectList,
)
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.runtime import WorkerMode, runtime_manager
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

        except PipelexError as exc:
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
        except PipelexError as exc:
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
                llm_prompt_factory=llm_prompt_factory_for_object or LLMPromptTemplate.make_for_structuring_from_preliminary_text(),
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
        except PipelexError as exc:
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
                llm_prompt_factory=llm_prompt_factory_for_object_list or LLMPromptTemplate.make_for_structuring_from_preliminary_text(),
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
        except PipelexError as exc:
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
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> GeneratedImageRawDetails:
        img_gen_config = get_config().cogt.img_gen_config
        try:
            # We're using workflowWfMakeImages which can generate several images but we're asking for only one
            img_gen_assignment = ImgGenAssignment(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=img_gen_prompt,
                img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
                img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
                nb_images=1,
            )

            generated_image_list = (
                await WorkflowExecutorFactory[ImgGenAssignment, list[GeneratedImageRawDetails]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeImages,
                    workflow_arg=img_gen_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-image"),
                )
            )
            if len(generated_image_list) != 1:
                msg = f"Expected 1 image, got {len(generated_image_list)}"
                raise ContentGenerationError(msg)
            generated_image = generated_image_list[0]
        except PipelexError as exc:
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
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[GeneratedImageRawDetails]:
        img_gen_config = get_config().cogt.img_gen_config
        try:
            img_gen_assignment = ImgGenAssignment(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=img_gen_prompt,
                img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
                img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
                nb_images=nb_images,
            )

            generated_image_list = (
                await WorkflowExecutorFactory[ImgGenAssignment, list[GeneratedImageRawDetails]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeImages,
                    workflow_arg=img_gen_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-image"),
                )
            )
        except PipelexError as exc:
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
        prompting_style: PromptingTarget | None = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
        wfid: str | None = None,
    ) -> str:
        jinja2_assignment = TemplatingAssignment(
            context=context,
            jinja2_name=jinja2_name,
            jinja2=jinja2,
            prompting_style=prompting_style,
            template_category=template_category,
        )
        jinja2_text = (
            await WorkflowExecutorFactory[TemplatingAssignment, str]
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
    async def make_extract_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
        wfid: str | None = None,
    ) -> ExtractOutput:
        try:
            extract_assignment = ExtractAssignment(
                job_metadata=job_metadata,
                extract_handle=extract_handle,
                extract_input=extract_input,
                extract_job_params=extract_job_params or ExtractJobParams.make_default_extract_job_params(),
                extract_job_config=extract_job_config or ExtractJobConfig(),
            )

            extract_output = (
                await WorkflowExecutorFactory[ExtractAssignment, ExtractOutput]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeOcr,
                    workflow_arg=extract_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "extract"),
                )
            )
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated extract output: {extract_output}")
        return extract_output
