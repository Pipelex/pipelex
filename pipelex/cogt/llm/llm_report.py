from typing import Any, Dict

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.inference_backend.model_spec import InferenceModelSpec
from pipelex.cogt.llm.token_category import CostCategory, CostsByCategoryDict, NbTokensByCategoryDict
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
    def report_field_for_nb_tokens_by_category(token_category: CostCategory) -> str:
        return f"nb_tokens_{token_category}"

    @staticmethod
    def report_field_for_cost_by_category(token_category: CostCategory) -> str:
        return f"cost_{token_category}"


class LLMTokenCostReport(BaseModel):
    job_metadata: JobMetadata
    llm_name: str
    platform_llm_id: str

    nb_tokens_by_category: NbTokensByCategoryDict
    costs_by_token_category: CostsByCategoryDict

    def as_flat_dictionary(self) -> Dict[str, Any]:
        the_dict: Dict[str, Any] = {}
        dict_for_job_metadata = self.job_metadata.model_dump(serialize_as_any=True)
        the_dict.update(dict_for_job_metadata)
        dict_for_llm: Dict[str, Any] = {
            LLMTokenCostReportField.LLM_NAME: self.llm_name,
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


def model_cost_per_token(inference_model: InferenceModelSpec, token_type: CostCategory) -> float:
    # cost_per_million_tokens_usd should be missing only for models that we run on our own GPUs
    if not inference_model.costs:
        log.warning(f"cost_per_million_tokens_usd is not set for model {inference_model.name}")
        return 0.0
    # all token types are not used for all models
    if token_type == CostCategory.INPUT_CACHED:
        if cost_per_million_tokens := inference_model.costs.get(CostCategory.INPUT_CACHED):
            return cost_per_million_tokens / 1000000
        elif cost_per_million_tokens := inference_model.costs.get(CostCategory.INPUT):
            # according to openai docs, cached input tokens are discounted 50%
            return 0.5 * cost_per_million_tokens / 1000000
        else:
            model = inference_model.name
            log.warning(f"cost is not set for model {model} neither for {CostCategory.INPUT} nor {CostCategory.INPUT_CACHED}")
            return 0.0
    elif token_type == CostCategory.INPUT_NON_CACHED:
        return model_cost_per_token(inference_model=inference_model, token_type=CostCategory.INPUT)
    elif cost_per_million_tokens := inference_model.costs.get(token_type):
        return cost_per_million_tokens / 1000000
    else:
        return 0.0


class LLMTokensUsage(BaseModel):
    job_metadata: JobMetadata
    llm_engine: InferenceModelSpec
    nb_tokens_by_category: NbTokensByCategoryDict

    def compute_cost_report(self) -> LLMTokenCostReport:
        costs_by_token_category: CostsByCategoryDict = {
            token_type: (model_cost_per_token(inference_model=self.llm_engine, token_type=token_type) * nb_tokens)
            for token_type, nb_tokens in self.nb_tokens_by_category.items()
        }
        token_cost_report = LLMTokenCostReport(
            job_metadata=self.job_metadata,
            llm_name=self.llm_engine.name,
            platform_llm_id=self.llm_engine.model_id,
            nb_tokens_by_category=self.nb_tokens_by_category,
            costs_by_token_category=costs_by_token_category,
        )
        return token_cost_report
