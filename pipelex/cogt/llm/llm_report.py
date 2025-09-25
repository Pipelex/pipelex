from typing import Any

from pydantic import BaseModel

from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.types import StrEnum


class LLMTokenCostReportField(StrEnum):
    LLM_NAME = "llm_name"
    PLATFORM_LLM_ID = "platform_llm_id"
    NB_TOKENS_INPUT = "nb_tokens_input"
    NB_TOKENS_INPUT_CACHED = "nb_tokens_input_cached"
    NB_TOKENS_INPUT_NON_CACHED = "nb_tokens_input_non_cached"
    NB_TOKENS_INPUT_JOINED = "nb_tokens_input_joined"  # joined = cached + non-cached
    NB_TOKENS_OUTPUT = "nb_tokens_output"
    COST_INPUT_CACHED = "cost_input_cached"
    COST_INPUT_NON_CACHED = "cost_input_non_cached"
    COST_INPUT_JOINED = "cost_input_joined"  # joined = cached + non-cached
    COST_OUTPUT = "cost_output"

    @staticmethod
    def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str:
        return f"nb_tokens_{token_category}"

    @staticmethod
    def report_field_for_cost_by_category(token_category: CostCategory) -> str:
        return f"cost_{token_category}"


class LLMTokenCostReport(BaseModel):
    job_metadata: JobMetadata
    inference_model_name: str
    platform_llm_id: str

    nb_tokens_by_category: NbTokensByCategoryDict
    costs_by_token_category: CostsByCategoryDict

    def as_flat_dictionary(self) -> dict[str, Any]:
        the_dict: dict[str, Any] = {}
        dict_for_job_metadata = self.job_metadata.model_dump(serialize_as_any=True)
        the_dict.update(dict_for_job_metadata)
        dict_for_llm: dict[str, Any] = {
            LLMTokenCostReportField.LLM_NAME: self.inference_model_name,
            LLMTokenCostReportField.PLATFORM_LLM_ID: self.platform_llm_id,
        }
        the_dict.update(dict_for_llm)
        dict_for_nb_tokens = {
            LLMTokenCostReportField.report_field_for_nb_tokens_by_category(token_category): nb_tokens
            for token_category, nb_tokens in self.nb_tokens_by_category.items()
        }
        the_dict.update(dict_for_nb_tokens)
        dict_for_costs = {
            LLMTokenCostReportField.report_field_for_cost_by_category(token_category): cost
            for token_category, cost in self.costs_by_token_category.items()
        }
        the_dict.update(dict_for_costs)
        return the_dict


class LLMTokensUsage(BaseModel):
    job_metadata: JobMetadata
    inference_model_name: str
    unit_costs: CostsByCategoryDict
    inference_model_id: str
    nb_tokens_by_category: NbTokensByCategoryDict
