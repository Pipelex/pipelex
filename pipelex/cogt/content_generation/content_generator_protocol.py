from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle
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

        updated_metadata = JobMetadata(
            content_generation_job_id=func.__name__,
        )
        job_metadata.update(updated_metadata=updated_metadata)

        return await func(*args, **kwargs)

    return wrapper


class ContentGeneratorProtocol(Protocol):
    async def make_llm_text(
        self,
        job_metadata: JobMetadata,
        llm_setting_main: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
    ) -> str: ...

    async def make_object_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
    ) -> BaseModelTypeVar: ...

    async def make_text_then_object(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: LLMPromptFactoryAbstract | None = None,
    ) -> BaseModelTypeVar: ...

    async def make_object_list_direct(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        nb_items: int | None = None,
    ) -> list[BaseModelTypeVar]: ...

    async def make_text_then_object_list(
        self,
        job_metadata: JobMetadata,
        object_class: type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: LLMPromptFactoryAbstract | None = None,
        nb_items: int | None = None,
    ) -> list[BaseModelTypeVar]: ...

    async def make_single_image(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> GeneratedImage: ...

    async def make_image_list(
        self,
        job_metadata: JobMetadata,
        img_gen_handle: str,
        img_gen_prompt: ImgGenPrompt,
        nb_images: int,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
    ) -> list[GeneratedImage]: ...

    async def make_jinja2_text(
        self,
        context: dict[str, Any],
        jinja2_name: str | None = None,
        jinja2: str | None = None,
        prompting_style: PromptingStyle | None = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
    ) -> str: ...

    async def make_ocr_extract_pages(
        self,
        job_metadata: JobMetadata,
        ocr_input: OcrInput,
        ocr_handle: str,
        ocr_job_params: OcrJobParams,
        ocr_job_config: OcrJobConfig,
    ) -> OcrOutput: ...
