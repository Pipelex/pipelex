from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    ObjectAssignment,
    RenderPageViewsAssignment,
    SearchAssignment,
    TemplatingAssignment,
)
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages_and_store
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.img_gen_generate import img_gen_image_list_and_store, img_gen_single_image_and_store
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_object
from pipelex.cogt.content_generation.render_generate import render_page_views_and_store
from pipelex.cogt.content_generation.search_generate import search_gen_sourced_answer, search_gen_structured_object
from pipelex.cogt.content_generation.templating_generate import templating_gen_text
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.runtime_hub import get_storage_provider
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGenerator(ContentGeneratorProtocol):
    def __init__(self, generated_content_factory: GeneratedContentFactory) -> None:
        self._generated_content_factory = generated_content_factory

    @classmethod
    def make_inline(cls) -> "ContentGenerator":
        """Inline generator wired to the hub storage provider.

        The single home for the in-process scopes' generator (``bundle_validator``,
        ``dry_run_pipeline``): under DRY its leaves mock without dispatching and without
        touching storage.
        """
        return cls(generated_content_factory=GeneratedContentFactory(storage_provider=get_storage_provider()))

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str:
        log.verbose(f"{self.__class__.__name__} make_llm_text: {llm_prompt_for_text}")
        log.verbose(f"llm_setting_main: {llm_setting_main}")
        llm_assignment = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            llm_setting=llm_setting_main,
            llm_prompt=llm_prompt_for_text,
        )
        log.verbose(llm_assignment.desc, title="llm_assignment")
        generated_text = await llm_gen_text(llm_assignment=llm_assignment)
        log.verbose(f"{self.__class__.__name__} generated text: {generated_text}")
        return generated_text

    @override
    @update_job_metadata
    async def make_object(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> BaseModelTypeVar:
        log.verbose(f"{self.__class__.__name__} make_object: {llm_prompt_for_object}")
        llm_assignment_for_object = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            llm_setting=llm_setting_for_object,
            llm_prompt=llm_prompt_for_object,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
        )
        raw_obj = await llm_gen_object(object_assignment=object_assignment, object_class=object_class)
        log.verbose(f"{self.__class__.__name__} generated object direct: {raw_obj}")
        return revalidate_leaf_object(raw_obj, object_class=object_class, is_mock_built=cogt_run_params.run_mode.is_dry)

    @override
    @update_job_metadata
    async def make_object_list(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> list[BaseModelTypeVar]:
        llm_assignment_for_object = LLMAssignment.make_from_prompt(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            llm_setting=llm_setting_for_object_list,
            llm_prompt=llm_prompt_for_object_list,
        )
        object_assignment = ObjectAssignment.make_for_class(
            object_class=object_class,
            llm_assignment=llm_assignment_for_object,
            nb_items=nb_items,
        )
        raw_list = await llm_gen_object_list(object_assignment=object_assignment, object_class=object_class)
        log.verbose(f"{self.__class__.__name__} generated object list direct: {raw_list}")
        return [revalidate_leaf_object(raw_obj, object_class=object_class, is_mock_built=cogt_run_params.run_mode.is_dry) for raw_obj in raw_list]

    @override
    @update_job_metadata
    async def make_single_image(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> ImageContent:
        img_gen_config = get_config().inference.img_gen
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job,
            nb_images=1,
        )
        image_content = await img_gen_single_image_and_store(
            img_gen_assignment=img_gen_assignment,
            generated_content_factory=self._generated_content_factory,
        )
        log.verbose(f"{self.__class__.__name__} generated image: {image_content}")
        return image_content

    @override
    @update_job_metadata
    async def make_image_list(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> list[ImageContent]:
        img_gen_config = get_config().inference.img_gen
        img_gen_assignment = ImgGenAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            img_gen_handle=img_gen_handle,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params or img_gen_config.make_default_img_gen_job_params(),
            img_gen_job_config=img_gen_job_config or img_gen_config.img_gen_job,
            nb_images=nb_images,
        )
        image_contents = await img_gen_image_list_and_store(
            img_gen_assignment=img_gen_assignment,
            generated_content_factory=self._generated_content_factory,
        )
        log.verbose(f"{self.__class__.__name__} generated image list: {image_contents}")
        return image_contents

    @override
    async def make_templated_text(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> str:
        templating_assignment = TemplatingAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            context=context,
            template=template,
            templating_style=templating_style,
            category=template_category or TemplateCategory.BASIC,
        )
        return await templating_gen_text(templating_assignment=templating_assignment)

    @override
    @update_job_metadata
    async def make_render_page_views(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> list[ImageContent]:
        if not extract_input.document_uri:
            msg = "PDF URI is required to render page views"
            raise ValueError(msg)
        job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        page_views_dpi = job_params.page_views_dpi or get_config().inference.extract.default_page_views_dpi
        render_assignment = RenderPageViewsAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            document_uri=extract_input.document_uri,
            page_views_dpi=page_views_dpi,
        )
        return await render_page_views_and_store(
            render_assignment=render_assignment,
            generated_content_factory=self._generated_content_factory,
        )

    @override
    @update_job_metadata
    async def make_extract_pages(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> list[PageContent]:
        extract_job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        extract_job_config = extract_job_config or ExtractJobConfig()
        extract_assignment = ExtractAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            extract_input=extract_input,
            extract_handle=extract_handle,
            extract_job_params=extract_job_params,
            extract_job_config=extract_job_config,
        )
        page_contents = await extract_gen_pages_and_store(
            extract_assignment=extract_assignment,
            generated_content_factory=self._generated_content_factory,
        )
        if extract_job_params and extract_job_params.should_include_page_views:
            page_view_contents: list[ImageContent] = []
            if extract_input.document_uri:
                page_view_contents = await self.make_render_page_views(
                    extract_input=extract_input,
                    extract_handle=extract_handle,
                    job_metadata=job_metadata,
                    cogt_run_params=cogt_run_params,
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

    @override
    async def make_search_sourced_answer(
        self,
        search_assignment: SearchAssignment,
    ) -> SearchResultContent:
        return await search_gen_sourced_answer(search_assignment=search_assignment)

    @override
    async def make_search_structured(
        self,
        *,
        output_structure_class: type[BaseModelTypeVar],
        search_assignment: SearchAssignment,
    ) -> BaseModelTypeVar:
        # In-process, so the caller's class travels down to the leaf exactly as it does on the object
        # paths, and comes back as an instance of itself — validated once, next to the provider. No
        # `SearchObjectAssignment` is built here: that wire model ships the class's schema across a
        # boundary, and this arm has none to cross.
        return await search_gen_structured_object(search_assignment, output_class=output_structure_class)
