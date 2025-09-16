from typing import Dict

from pipelex import log
from pipelex.cogt.llm.token_category import CostCategory


def model_cost_per_token(costs: Dict[CostCategory, float], token_type: CostCategory) -> float:
    # cost_per_million_tokens_usd should be missing only for models that we run on our own GPUs
    # all token types are not used for all models
    if token_type == CostCategory.INPUT_CACHED:
        if cost_per_million_tokens := costs.get(CostCategory.INPUT_CACHED):
            return cost_per_million_tokens / 1000000
        elif cost_per_million_tokens := costs.get(CostCategory.INPUT):
            # according to openai docs, cached input tokens are discounted 50%
            return 0.5 * cost_per_million_tokens / 1000000
        else:
            return 0.0
    elif token_type == CostCategory.INPUT_NON_CACHED:
        return model_cost_per_token(costs=costs, token_type=CostCategory.INPUT)
    elif cost_per_million_tokens := costs.get(token_type):
        return cost_per_million_tokens / 1000000
    else:
        return 0.0
