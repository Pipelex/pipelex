from typing import Any

from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.pipeline.job_metadata import JobMetadata


class LLMAssignment(BaseModel):
    job_metadata: JobMetadata
    llm_setting: LLMSetting
    llm_prompt: LLMPrompt

    @classmethod
    def make_from_prompt(
        cls,
        job_metadata: JobMetadata,
        llm_setting: LLMSetting,
        llm_prompt: LLMPrompt,
    ) -> "LLMAssignment":
        """Factory method for creating LLMAssignment from existing prompt."""
        return cls(
            job_metadata=job_metadata,
            llm_setting=llm_setting,
            llm_prompt=llm_prompt,
        )

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
        return self.llm_setting.model

    @property
    def llm_job_params(self) -> LLMJobParams:
        return self.llm_setting.make_llm_job_params()


class ObjectAssignment(BaseModel):
    object_class_name: str
    object_class_schema: dict[str, Any]
    llm_assignment_for_object: LLMAssignment

    @staticmethod
    def make_for_class(
        object_class: type[BaseModel],
        llm_assignment: LLMAssignment,
    ) -> "ObjectAssignment":
        return ObjectAssignment(
            object_class_name=object_class.__name__,
            object_class_schema=object_class.model_json_schema(),
            llm_assignment_for_object=llm_assignment,
        )


class ImgGenAssignment(BaseModel):
    job_metadata: JobMetadata
    img_gen_handle: str
    img_gen_prompt: ImgGenPrompt
    img_gen_job_params: ImgGenJobParams
    img_gen_job_config: ImgGenJobConfig
    nb_images: int


class TemplatingAssignment(BaseModel):
    job_metadata: JobMetadata
    context: dict[str, Any]
    template: str
    templating_style: TemplatingStyle | None = None
    category: TemplateCategory


class ExtractAssignment(BaseModel):
    job_metadata: JobMetadata
    extract_handle: str
    extract_input: ExtractInput
    extract_job_params: ExtractJobParams
    extract_job_config: ExtractJobConfig


class RenderPageViewsAssignment(BaseModel):
    job_metadata: JobMetadata
    document_uri: str
    page_views_dpi: int
