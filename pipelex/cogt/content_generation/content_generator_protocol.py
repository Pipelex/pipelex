from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
P = ParamSpec("P")
R = TypeVar("R")


def update_job_metadata(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # Attempt to get job_metadata from kwargs or from args
        job_metadata = kwargs.get("job_metadata")
        if job_metadata is None:
            msg = "job_metadata argument is required for this decorated function."
            raise RuntimeError(msg)

        if not isinstance(job_metadata, JobMetadata):
            msg = "The job_metadata argument must be of type JobMetadata."
            raise TypeError(msg)

        job_metadata.content_generation_job_id = func.__name__

        return await func(*args, **kwargs)

    return wrapper


class ContentGeneratorProtocol(Protocol):
    def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> Coroutine[Any, Any, str]: ...

    def make_object_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> Coroutine[Any, Any, BaseModelTypeVar]: ...

    def make_text_then_object(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: LLMPromptFactoryAbstract | None = None,
    ) -> Coroutine[Any, Any, BaseModelTypeVar]: ...

    def make_object_list_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> Coroutine[Any, Any, list[BaseModelTypeVar]]: ...

    def make_text_then_object_list(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: LLMPromptFactoryAbstract | None = None,
        nb_items: int | None = None,
    ) -> Coroutine[Any, Any, list[BaseModelTypeVar]]: ...

    async def make_image_content(
        self,
        job_metadata: JobMetadata,
        generated_image_raw_details: GeneratedImageRawDetails,
        img_gen_prompt: ImgGenPrompt | None,
    ) -> ImageContent: ...

    async def make_page_contents(
        self,
        job_metadata: JobMetadata,
        extract_output: ExtractOutput,
    ) -> list[PageContent]: ...

    def make_single_image(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> Coroutine[Any, Any, ImageContent]: ...

    def make_image_list(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> Coroutine[Any, Any, list[ImageContent]]: ...

    def make_templated_text(
        self,
        context: dict[str, Any],
        template: str,
        templating_style: TemplatingStyle | None = None,
        template_category: TemplateCategory | None = None,
    ) -> Coroutine[Any, Any, str]: ...

    async def make_render_page_views(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
    ) -> list[ImageContent]: ...

    def make_extract_pages(
        self,
        job_metadata: JobMetadata,
        extract_input: ExtractInput,
        extract_handle: str,
        extract_job_params: ExtractJobParams,
        extract_job_config: ExtractJobConfig,
    ) -> Coroutine[Any, Any, list[PageContent]]: ...
