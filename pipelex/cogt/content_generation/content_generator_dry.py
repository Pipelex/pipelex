from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from pipelex.urls import URLs


class ContentGeneratorDry(ContentGeneratorProtocol):
    """This class is used to generate mock content for testing purposes.
    It does not use any inference.
    """

    @property
    def _text_gen_truncate_length(self) -> int:
        return get_config().pipelex.dry_run_config.text_gen_truncate_length

    def _make_generated_image_fake(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> ImageContent:
        return ImageContent(
            url=raw_details.actual_url or URLs.jpg_example_1,
            public_url=raw_details.actual_url or URLs.jpg_example_1,
            mime_type=raw_details.mime_type or "image/jpeg",
            size=raw_details.size,
        )

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        wfid: str | None = None,
    ) -> str:
        func_name = "make_llm_text"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        prompt_truncated = llm_prompt_for_text.desc(truncate_text_length=self._text_gen_truncate_length)
        return f"DRY RUN: {func_name} • llm_setting={llm_setting_main.desc()} • prompt={prompt_truncated}"

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
        object_factory = DryRunFactory.make_dry_run_factory(object_class)
        # We run validators to ensure mock data is valid. Fields with format constraints
        # (snake_case, PascalCase, etc.) should have `examples` defined in their Field()
        # so polyfactory uses those instead of random strings.
        return object_factory.build()

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
        func_name = "make_text_then_object"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")

        return await self.make_object_direct(
            job_metadata=job_metadata,
            object_class=object_class,
            llm_setting_for_object=llm_setting_for_object,
            llm_prompt_for_object=llm_prompt_for_text,
        )

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
        func_name = "make_object_list_direct"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        nb_list_items = nb_items or get_config().pipelex.dry_run_config.nb_list_items
        items: list[BaseModelTypeVar] = []
        for idx in range(nb_list_items):
            item = await self.make_object_direct(
                job_metadata=job_metadata,
                object_class=object_class,
                llm_setting_for_object=llm_setting_for_object_list,
                llm_prompt_for_object=llm_prompt_for_object_list,
            )
            # Set first item's pipe_code to "mock_main" to coordinate with BundleHeaderSpec.main_pipe
            # which uses examples=["mock_main"] for dry run validation
            if idx == 0 and hasattr(item, "pipe_code"):
                item.pipe_code = "mock_main"  # pyright: ignore[reportAttributeAccessIssue]
            items.append(item)
        return items

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
        func_name = "make_text_then_object_list"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        return await self.make_object_list_direct(
            job_metadata=job_metadata,
            object_class=object_class,
            llm_setting_for_object_list=llm_setting_for_object_list,
            llm_prompt_for_object_list=llm_prompt_for_text,
            nb_items=nb_items,
        )

    @override
    async def make_image_content(
        self,
        job_metadata: JobMetadata,
        generated_image_raw_details: GeneratedImageRawDetails,
        img_gen_prompt: ImgGenPrompt | None,
    ) -> ImageContent:
        image_content = self._make_generated_image_fake(raw_details=generated_image_raw_details)
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
        page_contents: list[PageContent] = []
        for page_index in sorted(extract_output.pages.keys()):
            page = extract_output.pages[page_index]
            page_images: list[ImageContent] = []
            for extracted_image in page.extracted_images:
                image_content = await self.make_image_content(
                    job_metadata=job_metadata,
                    generated_image_raw_details=extracted_image,
                    img_gen_prompt=None,
                )
                page_images.append(image_content)
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=page_images,
                        raw_html=page.raw_html,
                    ),
                )
            )
        return page_contents

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
        func_name = "make_single_image"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        image_url = image_urls[0]
        return await self.make_image_content(
            job_metadata=job_metadata,
            generated_image_raw_details=GeneratedImageRawDetails(
                actual_url=image_url,
                size=ImageSize(width=1024, height=1024),
                mime_type="image/jpeg",
            ),
            img_gen_prompt=img_gen_prompt,
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
        wfid: str | None = None,
    ) -> list[ImageContent]:
        func_name = "make_image_list"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        image_contents: list[ImageContent] = []
        for image_index in range(nb_images):
            image_content = await self.make_image_content(
                job_metadata=job_metadata,
                generated_image_raw_details=GeneratedImageRawDetails(
                    actual_url=image_urls[image_index % len(image_urls)],
                    size=ImageSize(width=1024, height=1024),
                    mime_type="image/jpeg",
                ),
                img_gen_prompt=img_gen_prompt,
            )
            image_contents.append(image_content)
        return image_contents

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
        check_jinja2_parsing(template_source=template, template_category=template_category or TemplateCategory.BASIC)
        func_name = "make_templated_text"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        jinja2_truncated = template[: self._text_gen_truncate_length]
        return (
            f"DRY RUN: {func_name} • context={context} • "
            f"jinja2={jinja2_truncated} • templating_style={templating_style} • template_category={template_category}"
        )

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
            msg = "Document URI is required to render page views"
            raise ValueError(msg)
        nb_pages = get_config().pipelex.dry_run_config.nb_extract_pages
        page_view_images_resolved: list[ImageContent] = []
        for _ in range(1, nb_pages + 1):
            page_view_image = self._make_generated_image_fake(
                raw_details=GeneratedImageRawDetails(
                    actual_url=URLs.jpg_example_1,
                    size=ImageSize(width=1024, height=1024),
                    mime_type="image/jpeg",
                ),
            )
            page_view_images_resolved.append(page_view_image)
        return page_view_images_resolved

    @override
    @update_job_metadata
    async def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
        wfid: str | None = None,
    ) -> list[PageContent]:
        func_name = "make_extract_pages"
        log.verbose(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        nb_pages: int
        if extract_input.image_uri:
            nb_pages = 1
        else:
            nb_pages = get_config().pipelex.dry_run_config.nb_extract_pages
        page_contents: list[PageContent] = []
        for _ in range(1, nb_pages + 1):
            page = Page(
                text="DRY RUN: OCR text",
                extracted_images=[],
            )
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=[],
                    ),
                    page_view=None,
                )
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
