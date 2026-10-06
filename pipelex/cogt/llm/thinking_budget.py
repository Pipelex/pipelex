"""Fitting a manual thinking budget inside the bounds the model accepts and the output limit of the request that carries it.

Anthropic and Gemini count the thinking budget against `max_tokens`, so a budget that fills it leaves the
answer, a tool call on a structured output, nothing to be written in. The budget is cut to leave a quarter of
`max_tokens` for the answer, and held within the range the provider accepts for the model, which its spec
declares as the `min_thinking_budget` and `max_thinking_budget` valued constraints: Anthropic refuses a
`budget_tokens` below 1,024, and each Gemini 2.5 model has a range of its own.
"""

from pipelex.cogt.exceptions import LLMCapabilityError

# The share of max_tokens kept for the answer is 1 / THINKING_ANSWER_RESERVE_DIVISOR
THINKING_ANSWER_RESERVE_DIVISOR = 4


def fit_thinking_budget(*, budget: int, max_tokens: int | None, min_budget: int | None, max_budget: int | None, model_desc: str) -> int:
    """Return the thinking budget to send, given the budget asked for, the request's max_tokens and the model's bounds.

    Args:
        budget: The thinking budget resolved from the reasoning effort, or the explicit reasoning budget.
        max_tokens: The request's output limit, which the thinking budget counts against, or None when the request sets none.
        min_budget: The smallest budget the provider accepts for the model, or None when it declares none.
        max_budget: The largest budget the provider accepts for the model, or None when it declares none.
        model_desc: The model's description, for the error message.

    Returns:
        The budget, cut to max_budget and to leave a quarter of max_tokens (at least one token) for the answer, and raised to min_budget.

    Raises:
        LLMCapabilityError: When max_tokens cannot hold min_budget, or a single thinking token when the model declares no minimum,
            beside the answer reserve.

    """
    fitted_budget = budget
    if max_budget is not None:
        fitted_budget = min(fitted_budget, max_budget)
    if max_tokens is not None:
        answer_reserve = max(1, max_tokens // THINKING_ANSWER_RESERVE_DIVISOR)
        ceiling = max_tokens - answer_reserve
        smallest_budget = min_budget if min_budget is not None else 1
        if ceiling < smallest_budget:
            msg = (
                f"Model '{model_desc}' cannot think within max_tokens={max_tokens}: after reserving {answer_reserve} tokens for the answer, "
                f"{ceiling} remain for thinking, below the smallest thinking budget of {smallest_budget}. "
                f"Raise max_tokens or remove the reasoning setting."
            )
            raise LLMCapabilityError(msg)
        fitted_budget = min(fitted_budget, ceiling)
    if min_budget is not None:
        fitted_budget = max(fitted_budget, min_budget)
    return fitted_budget
