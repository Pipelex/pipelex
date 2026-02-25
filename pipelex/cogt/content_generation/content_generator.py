from typing import Any, cast

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
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.img_gen_generate import img_gen_image_list, img_gen_single_image
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.cogt.content_generation.templating_generate import templating_gen_text
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
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGenerator(ContentGeneratorProtocol):
    def __init__(self, generated_content_factory: GeneratedContentFactory) -> None:
        self._generated_content_factory = generated_content_factory

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str:
        log.verbose(f"{self.__class__.__name__} make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        llm_assignment = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        generated_text = await llm_gen_text(llm_assignment=llm_assignment)
        log.verbose(f"{self.__class__.__name__} generated text: {generated_text}")
        return generated_text

    @override
    @update_job_metadata
    async def make_object_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> BaseModelTypeVar:
        log.verbose(f"{self.__class__.__name__} make_object_direct: {llm_prompt_for_object}")
        llm_assignment_for_object = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        obj = await llm_gen_object(object_assignment=object_assignment)
        log.verbose(f"{self.__class__.__name__} generated object direct: {obj}")
        return cast("BaseModelTypeVar", obj)

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
    ) -> BaseModelTypeVar:
        log.verbose(llm_prompt_for_text.user_text, title="llm_prompt_for_text")
        llm_assignment_for_text = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )

        llm_assignment_factory_to_object = LLMAssignmentFactory(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object,
            llm_prompt_factory=llm_prompt_factory_for_object or LLMPromptTemplate.make_for_structuring_from_preliminary_text(),
        )

        workflow_arg = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        preliminary_text = await llm_gen_text(llm_assignment=llm_assignment_for_text)

        log.verbose(f"preliminary_text: {preliminary_text}")

        fup_llm_assignment = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
            preliminary_text=preliminary_text,
        )

        fup_obj_assignment = ObjectAssignment(
            llm_assignment_for_object=fup_llm_assignment,
            object_class_name=object_class.__name__,
        )

        obj = await llm_gen_object(object_assignment=fup_obj_assignment)
        log.verbose(f"{self.__class__.__name__} generated object after text: {obj}")
        return cast("BaseModelTypeVar", obj)

    @override
    @update_job_metadata
    async def make_object_list_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> list[BaseModelTypeVar]:
        llm_assignment_for_object = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        obj_list = await llm_gen_object_list(object_assignment=object_assignment)
        log.verbose(f"{self.__class__.__name__} generated object list direct: {obj_list}")
        return cast("list[BaseModelTypeVar]", obj_list)

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
    ) -> list[BaseModelTypeVar]:
        llm_assignment_for_text = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )

        llm_assignment_factory_to_object = LLMAssignmentFactory(
            job_metadata=job_metadata,
            llm_setting=llm_setting_for_object_list,
            llm_prompt_factory=llm_prompt_factory_for_object_list or LLMPromptTemplate.make_for_structuring_from_preliminary_text(),
        )
        workflow_arg = TextThenObjectAssignment(
            object_class_name=object_class.__name__,
            llm_assignment_for_text=llm_assignment_for_text,
            llm_assignment_factory_to_object=llm_assignment_factory_to_object,
        )

        preliminary_text = await llm_gen_text(llm_assignment=llm_assignment_for_text)

        log.verbose(f"preliminary_text: {preliminary_text}")

        fup_llm_assignment = await workflow_arg.llm_assignment_factory_to_object.make_llm_assignment(
            preliminary_text=preliminary_text,
        )

        fup_obj_assignment = ObjectAssignment(
            llm_assignment_for_object=fup_llm_assignment,
            object_class_name=object_class.__name__,
        )

        obj_list = await llm_gen_object_list(object_assignment=fup_obj_assignment)
        log.verbose(f"{self.__class__.__name__} generated object list after text: {obj_list}")
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
    @update_job_metadata
    async def make_single_image(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> ImageContent:
        img_gen_config = get_config().cogt.img_gen_config
        img_gen_job_params = img_gen_job_params or img_gen_config.make_default_img_gen_job_params()
        img_gen_job_config = img_gen_job_config or img_gen_config.img_gen_job_config
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params,
            img_gen_job_config=img_gen_job_config,
            nb_images=1,
        )
        generated_image_raw_details = await img_gen_single_image(img_gen_assignment=img_gen_assignment)
        log.verbose(f"{self.__class__.__name__} generated image raw details: {generated_image_raw_details}")
        return await self.make_image_content(
            job_metadata=job_metadata,
            img_gen_prompt=img_gen_prompt,
            generated_image_raw_details=generated_image_raw_details,
        )

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
    ) -> list[ImageContent]:
        img_gen_config = get_config().cogt.img_gen_config
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job_config,
            nb_images=nb_images,
        )
        generated_images_as_raw_details = await img_gen_image_list(img_gen_assignment=img_gen_assignment)
        log.verbose(f"{self.__class__.__name__} generated image list: {generated_images_as_raw_details}")
        return [
            await self.make_image_content(
                job_metadata=job_metadata,
                generated_image_raw_details=raw_details,
                img_gen_prompt=img_gen_prompt,
            )
            for raw_details in generated_images_as_raw_details
        ]

    @override
    async def make_templated_text(
        self,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> str:
        templating_assignment = TemplatingAssignment(
            context=context,
            template=template,
            templating_style=templating_style,
            category=template_category or TemplateCategory.BASIC,
        )
        return await templating_gen_text(templating_assignment=templating_assignment)

    @override
    async def make_render_page_views(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
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
    async def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> list[PageContent]:
        extract_job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        extract_job_config = extract_job_config or ExtractJobConfig()
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            extract_input=extract_input,
            extract_handle=extract_handle,
            extract_job_params=extract_job_params,
            extract_job_config=extract_job_config,
        )
        extract_output = await extract_gen_pages(extract_assignment=extract_assignment)
        page_contents = await self.make_page_contents(
            job_metadata=job_metadata,
            extract_output=extract_output,
        )
        if extract_job_params and extract_job_params.should_include_page_views:
            page_view_contents: list[ImageContent] = []
            if extract_input.document_uri:
                page_view_contents = await self.make_render_page_views(
                    extract_input=extract_input,
                    extract_handle=extract_handle,
                    job_metadata=job_metadata,
                    extract_job_params=extract_job_params,
                    extract_job_config=extract_job_config,
                )
            elif extract_input.image_uri:
                page_view_contents = [ImageContent(url=extract_input.image_uri)]
            if len(page_view_contents) != len(page_contents):
                msg = f"Number of page view contents ({len(page_view_contents)}) does not match number of page contents ({len(page_contents)})"
                raise ValueError(msg)
            for page_content in page_contents:
                page_content.page_view = page_view_contents.pop(0)

        return page_contents
