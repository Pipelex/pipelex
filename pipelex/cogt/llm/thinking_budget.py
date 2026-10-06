"""Fitting a manual thinking budget inside the output limit of the request that carries it.

Anthropic and Gemini count the thinking budget against `max_tokens`, so a budget that fills it leaves the
answer, a tool call on a structured output, nothing to be written in. The budget is cut to leave a quarter of
`max_tokens` for the answer, and raised to the provider's minimum where it has one: Anthropic refuses a
`budget_tokens` below 1,024 by name.
"""

from pipelex.cogt.exceptions import LLMCapabilityError

# The share of max_tokens kept for the answer is 1 / THINKING_ANSWER_RESERVE_DIVISOR
THINKING_ANSWER_RESERVE_DIVISOR = 4


def fit_thinking_budget(*, budget: int, max_tokens: int, min_budget: int | None, model_desc: str) -> int:
    """Return the thinking budget to send, given the budget asked for and the request's max_tokens.

    Args:
        budget: The thinking budget resolved from the reasoning effort, or the explicit reasoning budget.
        max_tokens: The request's output limit, which the thinking budget counts against.
        min_budget: The smallest budget the provider accepts, or None when it takes any.
        model_desc: The model's description, for the error message.

    Returns:
        The budget, cut to leave a quarter of max_tokens for the answer and raised to min_budget.

    Raises:
        LLMCapabilityError: When max_tokens cannot hold min_budget beside the answer reserve.

    """
    answer_reserve = max_tokens // THINKING_ANSWER_RESERVE_DIVISOR
    ceiling = max_tokens - answer_reserve
    if min_budget is not None and ceiling < min_budget:
        msg = (
            f"Model '{model_desc}' cannot think within max_tokens={max_tokens}: after reserving {answer_reserve} tokens for the answer, "
            f"{ceiling} remain for thinking, below the provider's minimum thinking budget of {min_budget}. "
            f"Raise max_tokens or remove the reasoning setting."
        )
        raise LLMCapabilityError(msg)
    fitted_budget = min(budget, ceiling)
    if min_budget is not None:
        fitted_budget = max(fitted_budget, min_budget)
    return fitted_budget
