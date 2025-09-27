from pipelex.cogt.usage.cost_category import CostCategory, CostsByCategoryDict


def model_cost_per_token(costs: CostsByCategoryDict, cost_category: CostCategory) -> float:
    # cost_per_million_tokens_usd should be missing only for models that we run on our own GPUs
    # all token types are not used for all models
    match cost_category:
        case CostCategory.INPUT_CACHED:
            if cost_per_million_tokens := costs.get(CostCategory.INPUT_CACHED):
                return cost_per_million_tokens / 1000000
            elif cost_per_million_tokens := costs.get(CostCategory.INPUT):
                # according to openai docs, cached input tokens are discounted 50%
                return 0.5 * cost_per_million_tokens / 1000000
            else:
                return 0.0
        case CostCategory.INPUT_NON_CACHED:
            return model_cost_per_token(costs=costs, cost_category=CostCategory.INPUT)
        case (
            CostCategory.INPUT
            | CostCategory.INPUT_JOINED
            | CostCategory.INPUT_AUDIO
            | CostCategory.OUTPUT
            | CostCategory.OUTPUT_AUDIO
            | CostCategory.OUTPUT_REASONING
            | CostCategory.OUTPUT_ACCEPTED_PREDICTION
            | CostCategory.OUTPUT_REJECTED_PREDICTION
        ):
            if cost_per_million_tokens := costs.get(cost_category):
                return cost_per_million_tokens / 1000000
            else:
                return 0.0
