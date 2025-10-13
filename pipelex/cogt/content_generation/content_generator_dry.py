from typing import Any

from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

DRY_BASE_64_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFUlEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC"


class ContentGeneratorDry(ContentGeneratorProtocol):
    """This class is used to generate mock content for testing purposes.
    It does not use any inference.
    """

    @property
    def _text_gen_truncate_length(self) -> int:
        return get_config().pipelex.dry_run_config.text_gen_truncate_length

    @override
    @update_job_metadata
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str:
        func_name = "make_llm_text"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
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
    ) -> BaseModelTypeVar:
        func_name = "make_object_direct"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")

        class ObjectFactory(ModelFactory[object_class]):  # type: ignore[valid-type]
            __model__ = object_class
            __check_model__ = True
            __use_examples__ = True
            __allow_none_optionals__ = False  # Ensure Optional fields always get values

        # `factory_use_contruct=True` prevents from running the model_validator/field_validator.
        # It is that way because the dry run was failing a lot of pipes that had validation test on the
        # field values. For example, if a string requires to be a snake_case, the ObjectFactory would
        # generate something like `DOIJZjoDoIJDZOjDZJo` which is... not a snake_case.
        return ObjectFactory.build(factory_use_construct=True)

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
        func_name = "make_text_then_object"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")

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
    ) -> list[BaseModelTypeVar]:
        func_name = "make_object_list_direct"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        nb_list_items = nb_items or get_config().pipelex.dry_run_config.nb_list_items
        return [
            await self.make_object_direct(
                job_metadata=job_metadata,
                object_class=object_class,
                llm_setting_for_object=llm_setting_for_object_list,
                llm_prompt_for_object=llm_prompt_for_object_list,
            )
            for _ in range(nb_list_items)
        ]

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
        func_name = "make_text_then_object_list"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        return await self.make_object_list_direct(
            job_metadata=job_metadata,
            object_class=object_class,
            llm_setting_for_object_list=llm_setting_for_object_list,
            llm_prompt_for_object_list=llm_prompt_for_text,
            nb_items=nb_items,
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
    ) -> GeneratedImage:
        func_name = "make_single_image"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        image_url = image_urls[0]
        return GeneratedImage(
            url=image_url,
            width=1536,
            height=2752,
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
    ) -> list[GeneratedImage]:
        func_name = "make_image_list"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        return [
            GeneratedImage(
                url=image_urls[image_index % len(image_urls)],
                width=1536,
                height=2752,
            )
            for image_index in range(nb_images)
        ]

    @override
    async def make_templated_text(
        self,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> str:
        check_jinja2_parsing(template_source=template, template_category=template_category or TemplateCategory.BASIC)
        func_name = "make_templated_text"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        jinja2_truncated = template[: self._text_gen_truncate_length]
        return (
            f"DRY RUN: {func_name} • context={context} • "
            f"jinja2={jinja2_truncated} • templating_style={templating_style} • template_category={template_category}"
        )

    @override
    async def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> ExtractOutput:
        func_name = "make_extract_pages"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        if extract_input.image_uri:
            image_as_page = Page(
                text="DRY RUN: OCR text",
                extracted_images=[],
                page_view=None,
            )
            extract_output = ExtractOutput(
                pages={1: image_as_page},
            )
        else:
            nb_pages = get_config().pipelex.dry_run_config.nb_extract_pages
            pages = {
                page_index: Page(
                    text="DRY RUN: OCR text",
                    extracted_images=[],
                    page_view=ExtractedImageFromPage(
                        image_id=f"page_view_{page_index}",
                        base_64=DRY_BASE_64_IMAGE,
                        caption="DRY RUN: OCR text",
                    ),
                )
                for page_index in range(1, nb_pages + 1)
            }
            extract_output = ExtractOutput(pages=pages)
        return extract_output
