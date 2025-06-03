from typing import Any, Dict, Optional, Type

from kajson.class_registry import class_registry
from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import LLMAssignmentError
from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.templating.jinja2_environment import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle


class LLMAssignmentFactory(BaseModel):
    job_metadata: JobMetadata
    llm_setting: LLMSetting
    llm_prompt_factory: LLMPromptFactoryAbstract

    async def make_llm_assignment(
        self,
        job_metadata: Optional[JobMetadata] = None,
        llm_setting: Optional[LLMSetting] = None,
        **prompt_arguments: Any,
    ) -> "LLMAssignment":
        log.verbose(f"Making LLMAssignment with prompt arguments: {prompt_arguments}, using {self.llm_prompt_factory.desc}")
        llm_prompt = await self.llm_prompt_factory.make_llm_prompt_from_args(**prompt_arguments)
        return LLMAssignment(
            job_metadata=job_metadata or self.job_metadata,
            llm_setting=llm_setting or self.llm_setting,
            llm_prompt=llm_prompt,
        )


class LLMAssignment(BaseModel):
    job_metadata: JobMetadata
    llm_setting: LLMSetting
    llm_prompt: LLMPrompt

    def clone_with_new_prompt(self, new_prompt: LLMPrompt) -> "LLMAssignment":
        return LLMAssignment(
            job_metadata=self.job_metadata,
            llm_setting=self.llm_setting,
            llm_prompt=new_prompt,
        )

    @property
    def desc(self) -> str:
        description = "LLMAssignment:"
        description += f"\n  llm_setting: {self.llm_setting}\n"
        description += f"\n  llm_prompt: {self.llm_prompt}\n"
        return description

    @override
    def __str__(self) -> str:
        return self.desc

    @property
    def llm_handle(self) -> str:
        log.dev(f"Using llm_setting {self.llm_setting}")
        return self.llm_setting.llm_handle

    @property
    def llm_job_params(self) -> LLMJobParams:
        return self.llm_setting.make_llm_job_params()


class ObjectAssignment(BaseModel):
    object_class_name: str
    llm_assignment_for_object: LLMAssignment

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        if not class_registry.has_class(name=self.object_class_name):
            error_msg = f"Could not create ObjectAssignment for class '{self.object_class_name}' because it is not in the class registry."
            raise LLMAssignmentError(error_msg)

    @staticmethod
    def make_for_class(
        object_class: Type[BaseModel],
        llm_assignment: LLMAssignment,
    ) -> "ObjectAssignment":
        object_class_name = object_class.__name__
        class_registry.register_class(
            class_type=object_class,
            name=object_class_name,
            should_warn_if_already_registered=False,
        )

        return ObjectAssignment(
            object_class_name=object_class_name,
            llm_assignment_for_object=llm_assignment,
        )


class TextThenObjectAssignment(BaseModel):
    object_class_name: str
    llm_assignment_for_text: LLMAssignment
    llm_assignment_factory_to_object: LLMAssignmentFactory


class ImggAssignment(BaseModel):
    job_metadata: JobMetadata
    imgg_handle: ImggHandle
    imgg_prompt: ImggPrompt
    imgg_job_params: ImggJobParams
    imgg_job_config: ImggJobConfig
    nb_images: int


class Jinja2Assignment(BaseModel):
    context: Dict[str, Any]
    jinja2_name: Optional[str] = None
    jinja2: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT


class OcrAssignment(BaseModel):
    job_metadata: JobMetadata
    ocr_handle: OcrHandle
    ocr_input: OcrInput
    ocr_job_params: OcrJobParams
    ocr_job_config: OcrJobConfig
