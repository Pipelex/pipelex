from functools import wraps
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional, ParamSpec, Protocol, Type, TypeVar

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
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_environment import Jinja2TemplateCategory
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
            raise RuntimeError("job_metadata argument is required for this decorated function.")

        if not isinstance(job_metadata, JobMetadata):
            raise TypeError("The job_metadata argument must be of type JobMetadata.")

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
        wfid: Optional[str] = None,
    ) -> str: ...

    async def make_object_direct(
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        wfid: Optional[str] = None,
    ) -> BaseModelTypeVar: ...

    async def make_text_then_object(
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object: Optional[LLMPromptFactoryAbstract] = None,
        wfid: Optional[str] = None,
    ) -> BaseModelTypeVar: ...

    async def make_object_list_direct(
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_object_list: LLMPrompt,
        wfid: Optional[str] = None,
    ) -> List[BaseModelTypeVar]: ...

    async def make_text_then_object_list(
        self,
        job_metadata: JobMetadata,
        object_class: Type[BaseModelTypeVar],
        llm_setting_main: LLMSetting,
        llm_setting_for_object_list: LLMSetting,
        llm_prompt_for_text: LLMPrompt,
        llm_prompt_factory_for_object_list: Optional[LLMPromptFactoryAbstract] = None,
        wfid: Optional[str] = None,
    ) -> List[BaseModelTypeVar]: ...

    async def make_single_image(
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        wfid: Optional[str] = None,
    ) -> GeneratedImage: ...

    async def make_image_list(
        self,
        job_metadata: JobMetadata,
        imgg_handle: ImggHandle,
        imgg_prompt: ImggPrompt,
        nb_images: int,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        wfid: Optional[str] = None,
    ) -> List[GeneratedImage]: ...

    async def make_jinja2_text(
        self,
        context: Dict[str, Any],
        jinja2_name: Optional[str] = None,
        jinja2: Optional[str] = None,
        prompting_style: Optional[PromptingStyle] = None,
        template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
        wfid: Optional[str] = None,
    ) -> str: ...

    async def make_ocr_extract_pages(
        self,
        job_metadata: JobMetadata,
        ocr_input: OcrInput,
        ocr_handle: OcrHandle,
        ocr_job_params: OcrJobParams,
        ocr_job_config: OcrJobConfig,
        wfid: Optional[str] = None,
    ) -> OcrOutput: ...
