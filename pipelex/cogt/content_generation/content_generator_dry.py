from typing import Any, Dict, List, Optional, Type

from polyfactory.factories.pydantic_factory import ModelFactory
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol, update_job_metadata
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.cogt.ocr.ocr_output import ExtractedImageFromPage, OcrOutput, Page
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class ContentGeneratorDry(ContentGeneratorProtocol):
    """
    This class is used to generate mock content for testing purposes.
    It does not use any inference.
    """

    @property
    def _text_gen_truncate_length(self) -> int:
        return get_config().pipelex.dry_run_config.text_gen_truncate_length

    @override
    @update_job_metadata
    async def make_llm_text(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str:
        func_name = "make_llm_text"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        prompt_truncated = llm_prompt_for_text.desc(truncate_text_length=self._text_gen_truncate_length)
        generated_text = f"DRY RUN: {func_name} • llm_setting={llm_setting_main.desc()} • prompt={prompt_truncated}"
        return generated_text

    @override
    @update_job_metadata
    async def make_object_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> BaseModelTypeVar:
        func_name = "make_object_direct"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")

        class ObjectFactory(ModelFactory[object_class]):  # type: ignore
            __model__ = object_class
            __check_model__ = True
            __use_examples__ = True
            __allow_none_optionals__ = False  # Ensure Optional fields always get values

        obj = ObjectFactory.build()
        return obj

    @override
    @update_job_metadata
    async def make_text_then_object(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: Optional[LLMPromptFactoryAbstract] = None,
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
    async def make_object_list_direct(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: Optional[int] = None,
    ) -> List[BaseModelTypeVar]:
        func_name = "make_object_list_direct"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        nb_list_items = nb_items or get_config().pipelex.dry_run_config.nb_list_items
        objects = [
            await self.make_object_direct(
                job_metadata=job_metadata,
                object_class=object_class,
                llm_setting_for_object=llm_setting_for_object_list,
                llm_prompt_for_object=llm_prompt_for_object_list,
            )
            for _ in range(nb_list_items)
        ]
        return objects

    @override
    @update_job_metadata
    async def make_text_then_object_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: Optional[LLMPromptFactoryAbstract] = None,
        nb_items: Optional[int] = None,
    ) -> List[BaseModelTypeVar]:
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
    async def make_single_image(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
    ) -> GeneratedImage:
        func_name = "make_single_image"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        image_url = image_urls[0]
        generated_image = GeneratedImage(
            url=image_url,
            width=1536,
            height=2752,
        )
        return generated_image

    @override
    @update_job_metadata
    async def make_image_list(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        nb_images: int,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
    ) -> List[GeneratedImage]:
        func_name = "make_image_list"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        image_urls = get_config().pipelex.dry_run_config.image_urls
        generated_image_list = [
            GeneratedImage(
                url=image_urls[image_index % len(image_urls)],
                width=1536,
                height=2752,
            )
            for image_index in range(nb_images)
        ]
        return generated_image_list

    @override
    async def make_jinja2_text(
        self,
        context: Dict[str, Any],
        jinja2_name: Optional[str] = None,
        jinja2: Optional[str] = None,
        prompting_style: Optional[PromptingStyle] = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
    ) -> str:
        # TODO: Use the code that checks if the jinja2 is a valid template
        func_name = "make_jinja2_text"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        jinja2_truncated = jinja2[: self._text_gen_truncate_length] if jinja2 else None
        jinja2_text = (
            f"DRY RUN: {func_name} • context={context} • jinja2_name={jinja2_name} • "
            f"jinja2={jinja2_truncated} • prompting_style={prompting_style} • template_category={template_category}"
        )
        return jinja2_text

    @override
    async def make_ocr_extract_pages(
        self,
        job_metadata: JobMetadata,
        ocr_input: OcrInput,
        ocr_handle: OcrHandle,
        ocr_job_params: Optional[OcrJobParams] = None,
        ocr_job_config: Optional[OcrJobConfig] = None,
    ) -> OcrOutput:
        func_name = "make_ocr_extract_pages"
        log.dev(f"🤡 DRY RUN: {self.__class__.__name__}.{func_name}")
        if ocr_input.image_uri:
            ocr_image_as_page = Page(
                text="DRY RUN: OCR text",
                extracted_images=[],
                page_view=None,
            )
            ocr_output = OcrOutput(
                pages={1: ocr_image_as_page},
            )
        else:
            nb_pages = get_config().pipelex.dry_run_config.nb_ocr_pages
            pages = {
                page_index: Page(
                    text="DRY RUN: OCR text",
                    extracted_images=[],
                    page_view=ExtractedImageFromPage(
                        image_id=f"page_view_{page_index}",
                        base_64="",
                        caption="DRY RUN: OCR text",
                    ),
                )
                for page_index in range(1, nb_pages + 1)
            }
            ocr_output = OcrOutput(pages=pages)
        return ocr_output
