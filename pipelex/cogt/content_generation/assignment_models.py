from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.pipeline.job_metadata import JobMetadata


class LLMAssignment(BaseModel):
    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    llm_setting: LLMSetting
    llm_prompt: LLMPrompt

    @classmethod
    def make_from_prompt(
        cls,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        llm_setting: LLMSetting,
        llm_prompt: LLMPrompt,
    ) -> "LLMAssignment":
        """Factory method for creating LLMAssignment from existing prompt."""
        return cls(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            llm_setting=llm_setting,
            llm_prompt=llm_prompt,
        )

    def clone_with_new_prompt(self, new_prompt: LLMPrompt) -> "LLMAssignment":
        return LLMAssignment(
            job_metadata=self.job_metadata,
            cogt_run_params=self.cogt_run_params,
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
    # Fixed list size for object-list generation (None = leaf mock falls back to
    # `dry_run_config.nb_list_items`). Carried on the assignment so the leaf mock
    # preserves fixed-size list lengths on any backend (eng review D11). ge=0: a negative
    # count must fail loud at construction, not silently mock an empty list.
    nb_items: int | None = Field(default=None, ge=0)

    @property
    def cogt_run_params(self) -> CogtRunParams:
        """Delegates to the nested LLM assignment — single copy, no duplication."""
        return self.llm_assignment_for_object.cogt_run_params

    @staticmethod
    def make_for_class(
        object_class: type[BaseModel],
        *,
        llm_assignment: LLMAssignment,
        nb_items: int | None = None,
    ) -> "ObjectAssignment":
        return ObjectAssignment(
            object_class_name=object_class.__name__,
            object_class_schema=object_class.model_json_schema(),
            llm_assignment_for_object=llm_assignment,
            nb_items=nb_items,
        )


class ImgGenAssignment(BaseModel):
    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    img_gen_handle: str
    img_gen_prompt: ImgGenPrompt
    img_gen_job_params: ImgGenJobParams
    img_gen_job_config: ImgGenJobConfig
    nb_images: int


class TemplatingAssignment(BaseModel):
    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    context: dict[str, Any]
    template: str
    templating_style: TemplatingStyle | None = None
    category: TemplateCategory


class ExtractAssignment(BaseModel):
    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    extract_handle: str
    extract_input: ExtractInput
    extract_job_params: ExtractJobParams
    extract_job_config: ExtractJobConfig


class RenderPageViewsAssignment(BaseModel):
    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    document_uri: str
    page_views_dpi: int


class SearchAssignment(BaseModel):
    """Serializable unit for a single web-search leaf call.

    Carries everything the framework-agnostic ``search_generate`` core needs to rebuild the
    ``SearchJob`` on the other side of the Temporal boundary: the rendered ``query``, the fully
    resolved ``search_setting`` (its ``model`` is the resolved provider handle, also the routing
    key), and the per-call domain/date overrides. Mirrors ``LLMAssignment`` for the LLM leaf.
    """

    job_metadata: JobMetadata
    cogt_run_params: CogtRunParams
    query: str
    search_setting: SearchSetting
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    from_date: str | None = None
    to_date: str | None = None

    @property
    def search_handle(self) -> str:
        return self.search_setting.model


class SearchObjectAssignment(BaseModel):
    """Structured-search counterpart of ``ObjectAssignment``.

    Ships the output structure's JSON schema (not the live class) across the boundary so the
    activity can reconstruct a throwaway class via ``SchemaToModelFactory`` for the provider call.
    The submitter re-validates the returned dict against the original class.
    """

    output_class_name: str
    output_class_schema: dict[str, Any]
    search_assignment: SearchAssignment

    @property
    def cogt_run_params(self) -> CogtRunParams:
        """Delegates to the nested search assignment — single copy, no duplication."""
        return self.search_assignment.cogt_run_params

    @staticmethod
    def make_for_class(
        output_class: type[BaseModel],
        *,
        search_assignment: SearchAssignment,
    ) -> "SearchObjectAssignment":
        return SearchObjectAssignment(
            output_class_name=output_class.__name__,
            output_class_schema=output_class.model_json_schema(),
            search_assignment=search_assignment,
        )
