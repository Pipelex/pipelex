from typing import Any, cast

from pydantic import BaseModel  # noqa: TC002
from typing_extensions import override

from pipelex import log
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
from pipelex.temporal.exceptions import ContentGenerationError
from pipelex.temporal.tprl.conditional_worker import with_conditional_worker
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
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
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGeneratorTop(WorkflowExecutor[AssignmentType, ResultType], ContentGeneratorProtocol):
    def __init__(self, generated_content_factory: GeneratedContentFactory, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._generated_content_factory = generated_content_factory

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: str | None = None,
    ) -> str:
        log.verbose(f"TopCrafter make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text")
        llm_assignment = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        temporal_client = await self.temporal_client()
        generated_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeLLMText.run,
            arg=llm_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated text: {generated_text}")
        return generated_text

    @override
    @with_conditional_worker
    @update_job_metadata
    async def make_object_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        wfid: str | None = None,
    ) -> BaseModelTypeVar:
        log.verbose(f"TopCrafter make_object_direct: {llm_prompt_for_object}")
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-object-direct")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        temporal_client = await self.temporal_client()
        obj = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeObject.run,
            arg=object_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object direct: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text-then-object")

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

        temporal_client = await self.temporal_client()
        obj = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeTextThenObject.run,
            arg=tto_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object after text: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-object-list-direct")
        llm_assignment_for_object = LLMAssignment(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        temporal_client = await self.temporal_client()
        obj_list: list[BaseModel] = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeObjectList.run,
            arg=object_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object list direct: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

    @override
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-text-then-object-list")

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

        temporal_client = await self.temporal_client()
        obj_list: list[BaseModel] = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeTextThenObjectList.run,
            arg=tto_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.verbose(f"TopCrafter generated object list after text: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

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
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-image")
        img_gen_config = get_config().cogt.img_gen_config
        # We're using workflowWfMakeImages which can generate several images but we're asking for only one
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=1,
        )
        temporal_client = await self.temporal_client()
        generated_image_list = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeImages.run,
            arg=img_gen_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        if len(generated_image_list) != 1:
            msg = f"Expected 1 image, got {len(generated_image_list)}"
            raise ContentGenerationError(msg)
        generated_image = generated_image_list[0]
        log.dev(f"TopCrafter generated image: {generated_image}")
        return await self.make_image_content(
            job_metadata=job_metadata,
            generated_image_raw_details=generated_image,
            img_gen_prompt=img_gen_prompt,
        )

    @override
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "craft-image")
        img_gen_config = get_config().cogt.img_gen_config
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=nb_images,
        )
        temporal_client = await self.temporal_client()
        generated_image_list = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeImages.run,
            arg=img_gen_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.dev(f"TopCrafter generated image list: {generated_image_list}")
        return [
            await self.make_image_content(
                job_metadata=job_metadata,
                generated_image_raw_details=raw_details,
                img_gen_prompt=img_gen_prompt,
            )
            for raw_details in generated_image_list
        ]

    @override
    @with_conditional_worker
    async def make_templated_text(
        self,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
        wfid: str | None = None,
    ) -> str:
        workflow_id = self.make_workflow_id(base_id=wfid or "jinja2-text")
        templating_assignment = TemplatingAssignment(
            context=context,
            template=template,
            templating_style=templating_style,
            category=template_category or TemplateCategory.BASIC,
        )
        temporal_client = await self.temporal_client()
        jinja2_text = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            WfMakeJinja2Text.run,
            arg=templating_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.dev(f"TopCrafter templated text: {jinja2_text}")
        return jinja2_text

    @override
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
        page_view_images = await pypdfium2_renderer.render_pdf_pages_from_uri(pdf_uri=extract_input.document_uri, dpi=page_views_dpi)
        page_view_images_resolved: list[ImageContent] = []
        for page_view_image in page_view_images:
            image_content = await self.make_image_content(
                job_metadata=job_metadata,
                generated_image_raw_details=GeneratedImageRawDetails.make_from_pil_image(
                    pil_image=page_view_image,
                    image_format=ImageFormat.PNG,
                ),
                img_gen_prompt=None,
            )
            page_view_images_resolved.append(image_content)

        return page_view_images_resolved

    @override
    @with_conditional_worker
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
        workflow_id = self.make_workflow_id(base_id=wfid or "extract")
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            extract_handle=extract_handle,
            extract_input=extract_input,
            extract_job_params=extract_job_params,
            extract_job_config=extract_job_config,
        )
        temporal_client = await self.temporal_client()
        extract_output = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfMakeExtract.run,
            arg=extract_assignment,
            id=workflow_id,
            task_queue=self.task_queue or get_config().temporal.worker_config.task_queue,
            execution_timeout=self.execution_timeout,
            retry_policy=self.retry_policy,
        )
        log.dev(f"TopCrafter extract output: {extract_output}")
        return await self.make_page_contents(job_metadata=job_metadata, extract_output=extract_output)
