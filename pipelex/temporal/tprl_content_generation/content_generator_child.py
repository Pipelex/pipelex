from typing import Any

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
    RenderPageViewsAssignment,
    TemplatingAssignment,
    TextThenObjectAssignment,
)
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
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
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.runtime import WorkerMode, runtime_manager
from pipelex.temporal.exceptions import ContentGenerationError
from pipelex.temporal.tprl.temporal_error import TemporalError
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor, WorkflowExecutorFactory
from pipelex.temporal.tprl_content_generation.content_generator_models import AssignmentType, ResultType
from pipelex.temporal.tprl_content_generation.wf_make_extract import WfMakeExtract
from pipelex.temporal.tprl_content_generation.wf_make_images import WfMakeImages
from pipelex.temporal.tprl_content_generation.wf_make_jinja2_text import WfMakeJinja2Text
from pipelex.temporal.tprl_content_generation.wf_make_llm_text import WfMakeLLMText
from pipelex.temporal.tprl_content_generation.wf_make_object import (
    WfMakeObject,
    WfMakeObjectList,
    WfMakeTextThenObject,
    WfMakeTextThenObjectList,
)
from pipelex.temporal.tprl_content_generation.wf_render_page_views import WfRenderPageViews
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
    def __init__(self, generated_content_factory: GeneratedContentFactory, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._generated_content_factory = generated_content_factory

    @override
    @update_job_metadata
    async def make_llm_text(
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
    async def make_object_direct(
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
        return object_class.model_validate(obj.model_dump(serialize_as_any=True))

    @override
    @update_job_metadata
    async def make_text_then_object(
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
                object_class_schema=object_class.model_json_schema(),
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
        return object_class.model_validate(obj.model_dump(serialize_as_any=True))

    @override
    @update_job_metadata
    async def make_object_list_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
        wfid: str | None = None,
    ) -> list[BaseModelTypeVar]:
        try:
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
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild generated object list direct: {obj_list}")
        return [object_class.model_validate(raw_obj.model_dump(serialize_as_any=True)) for raw_obj in obj_list]

    @override
    @update_job_metadata
    async def make_text_then_object_list(
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
                object_class_schema=object_class.model_json_schema(),
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
        return [object_class.model_validate(raw_obj.model_dump(serialize_as_any=True)) for raw_obj in obj_list]

    @override
    async def make_image_content(
        self,
        job_metadata: JobMetadata,
        generated_image_raw_details: GeneratedImageRawDetails,
        img_gen_prompt: ImgGenPrompt | None,
    ) -> ImageContent:
        image_content = await self._generated_content_factory.make_image_content(
            primary_id=job_metadata.user_id,
            secondary_id=job_metadata.pipeline_run_id,
            raw_details=generated_image_raw_details,
        )
        if img_gen_prompt:
            image_content.source_prompt = img_gen_prompt.positive_text
            image_content.source_negative_prompt = img_gen_prompt.negative_text
        return image_content

    @override
    async def make_page_contents(
        self,
        job_metadata: JobMetadata,
        extract_output: ExtractOutput,
    ) -> list[PageContent]:
        return await self._generated_content_factory.make_page_contents(
            primary_id=job_metadata.user_id,
            secondary_id=job_metadata.pipeline_run_id,
            extract_output=extract_output,
        )

    @override
    @update_job_metadata
    async def make_single_image(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> ImageContent:
        img_gen_config = get_config().cogt.img_gen_config
        try:
            img_gen_assignment = ImgGenAssignment(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=img_gen_prompt,
                img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
                img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
                nb_images=1,
            )

            image_content_list = (
                await WorkflowExecutorFactory[ImgGenAssignment, list[ImageContent]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeImages,
                    workflow_arg=img_gen_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "craft-image"),
                )
            )
            if len(image_content_list) != 1:
                msg = f"Expected 1 image, got {len(image_content_list)}"
                raise ContentGenerationError(msg)
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        image_content = image_content_list[0]
        log.verbose(f"ContentGeneratorChild generated image: {image_content}")
        return image_content

    @override
    @update_job_metadata
    async def make_image_list(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[ImageContent]:
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

            image_content_list = (
                await WorkflowExecutorFactory[ImgGenAssignment, list[ImageContent]]
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
        log.verbose(f"ContentGeneratorChild generated image list: {image_content_list}")
        return image_content_list

    @override
    async def make_templated_text(
        self,
        job_metadata: JobMetadata,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
        wfid: str | None = None,
    ) -> str:
        try:
            templating_assignment = TemplatingAssignment(
                job_metadata=job_metadata,
                context=context,
                template=template,
                templating_style=templating_style,
                category=template_category or TemplateCategory.BASIC,
            )
            jinja2_text = (
                await WorkflowExecutorFactory[TemplatingAssignment, str]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeJinja2Text,
                    workflow_arg=templating_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "jinja2-text"),
                )
            )
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild templated text: {jinja2_text}")
        return jinja2_text

    @override
    @update_job_metadata
    async def make_render_page_views(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[ImageContent]:
        if not extract_input.document_uri:
            msg = "PDF URI is required to render page views"
            raise ValueError(msg)
        job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        page_views_dpi = job_params.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi
        try:
            render_assignment = RenderPageViewsAssignment(
                job_metadata=job_metadata,
                document_uri=extract_input.document_uri,
                page_views_dpi=page_views_dpi,
            )
            image_content_list = (
                await WorkflowExecutorFactory[RenderPageViewsAssignment, list[ImageContent]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfRenderPageViews,
                    workflow_arg=render_assignment,
                    workflow_id=make_child_workflow_id(base_id=wfid or "render-page-views"),
                )
            )
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc) from exc
        except ChildWorkflowError as exc:
            log.error(f"ChildWorkflowError caused by: {exc.cause}")
            if isinstance(exc.cause, ApplicationError):
                raise TemporalError.from_app_error(exc=exc.cause) from exc
            raise
        log.verbose(f"ContentGeneratorChild rendered page views: {image_content_list}")
        return image_content_list

    @override
    @update_job_metadata
    async def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams,
        extract_job_config: ExtractJobConfig,
        wfid: str | None = None,
    ) -> list[PageContent]:
        try:
            extract_assignment = ExtractAssignment(
                job_metadata=job_metadata,
                extract_handle=extract_handle,
                extract_input=extract_input,
                extract_job_params=extract_job_params,
                extract_job_config=extract_job_config,
            )

            page_content_list = (
                await WorkflowExecutorFactory[ExtractAssignment, list[PageContent]]
                .create_executor()
                .execute_child_workflow(
                    workflow_class=WfMakeExtract,
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
        log.verbose(f"ContentGeneratorChild generated page contents: {page_content_list}")
        return page_content_list
