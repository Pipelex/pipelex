from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.system.job_metadata import JobMetadata


class JudgmentTokenCostReportField(StrEnum):
    MODEL_TYPE = "model_type"
    JUDGMENT_NAME = "judgment_name"
    PLATFORM_JUDGMENT_ID = "platform_judgment_id"
    NB_TOKENS_INPUT_CACHED = "nb_tokens_input_cached"
    NB_TOKENS_INPUT_NON_CACHED = "nb_tokens_input_non_cached"
    NB_TOKENS_INPUT_JOINED = "nb_tokens_input_joined"
    NB_TOKENS_OUTPUT = "nb_tokens_output"
    COST_INPUT_CACHED = "cost_input_cached"
    COST_INPUT_NON_CACHED = "cost_input_non_cached"
    COST_INPUT_JOINED = "cost_input_joined"
    COST_OUTPUT = "cost_output"

    @staticmethod
    def report_field_for_nb_tokens_by_category(token_category: TokenCategory) -> str:
        return f"nb_tokens_{token_category}"

    @staticmethod
    def report_field_for_cost_by_category(token_category: CostCategory) -> str:
        return f"cost_{token_category}"


class JudgmentTokenCostReport(BaseModel):
    model_type: Literal["judgment"] = "judgment"
    job_metadata: JobMetadata
    inference_model_name: str
    platform_model_id: str

    nb_tokens_by_category: NbTokensByCategoryDict
    costs_by_token_category: CostsByCategoryDict

    def as_flat_dictionary(self) -> dict[str, Any]:
        the_dict: dict[str, Any] = {}
        dict_for_job_metadata = self.job_metadata.model_dump(serialize_as_any=True)
        the_dict.update(dict_for_job_metadata)
        dict_for_model: dict[str, Any] = {
            JudgmentTokenCostReportField.MODEL_TYPE: self.model_type,
            JudgmentTokenCostReportField.JUDGMENT_NAME: self.inference_model_name,
            JudgmentTokenCostReportField.PLATFORM_JUDGMENT_ID: self.platform_model_id,
        }
        the_dict.update(dict_for_model)
        dict_for_nb_tokens = {
            JudgmentTokenCostReportField.report_field_for_nb_tokens_by_category(token_category): nb_tokens
            for token_category, nb_tokens in self.nb_tokens_by_category.items()
        }
        the_dict.update(dict_for_nb_tokens)
        dict_for_costs = {
            JudgmentTokenCostReportField.report_field_for_cost_by_category(token_category): cost
            for token_category, cost in self.costs_by_token_category.items()
        }
        the_dict.update(dict_for_costs)
        return the_dict


class JudgmentTokensUsage(BaseModel):
    """Real input and output token counts, priced per million like an LLM's.

    This is where the family parts company with search, which encodes per-request billing as a token
    count: a judgment backend reports the tokens it actually read. A backend that reports no usage
    leaves ``nb_tokens_by_category`` empty rather than guessing, and the call reports as the
    zero-token attempt it was.
    """

    model_type: Literal["judgment"] = "judgment"
    job_metadata: JobMetadata
    inference_model_name: str
    unit_costs: CostsByCategoryDict
    inference_model_id: str
    nb_tokens_by_category: NbTokensByCategoryDict
