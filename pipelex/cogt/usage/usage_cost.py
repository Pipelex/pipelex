"""The cost of one inference call's usage, in US dollars: the one cost engine every report and event prices with.

The run's cost table, the client-facing usage records, the run graph's attribution and the event an inference call
ends with all price a usage here, so a usage gets the same price whichever of them reads it. The module holds the
arithmetic alone and imports nothing that renders, so a worker base prices the call it just made without importing the
console that the cost table prints through.

It is also where a worker whose provider bills by the request, or an extraction priced by its pages, records that
usage, with ``record_unit_priced_usage``, so the rates price each unit and every reader knows the counts are no tokens.
"""

from typing import Literal

from pipelex.cogt.extract.extract_report import ExtractTokensUsage
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.cogt.judgment.judgment_report import JudgmentTokensUsage
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.search.search_report import SearchTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.costs_per_token import model_cost_per_token
from pipelex.cogt.usage.pricing_unit import TOKENS_PER_PRICED_UNIT, PricingUnit
from pipelex.cogt.usage.token_category import TokenCategory

TokensUsage = LLMTokensUsage | ImgGenTokensUsage | ExtractTokensUsage | SearchTokensUsage | JudgmentTokensUsage


def compute_total_cost(*, input_non_cached_cost: float, input_cached_cost: float, output_cost: float) -> float:
    """The total of a call's component costs: what it read uncached, what it read from the cache, and what it wrote."""
    return input_non_cached_cost + input_cached_cost + output_cost


def compute_tokens_usage_cost(tokens_usage: TokensUsage) -> float | None:
    """Compute the canonical USD cost of a single inference call, or None when unrated.

    Returns ``None`` when the usage carries no rate table (``unit_costs`` is empty:
    own-GPU models, dry/mock runs). Otherwise returns the same canonical total the cost
    table reports for the call — input_non_cached + input_cached + output component
    costs, with the cached-discount fallback from ``model_cost_per_token``. Categories
    the cost engine excludes from totals (audio, reasoning, prediction) are excluded
    here too: one cost engine, one total.
    """
    if not tokens_usage.unit_costs:
        return None
    nb_tokens_input_joined = tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT, 0)
    nb_tokens_input_cached = tokens_usage.nb_tokens_by_category.get(TokenCategory.INPUT_CACHED, 0)
    nb_tokens_input_non_cached = nb_tokens_input_joined - nb_tokens_input_cached
    nb_tokens_output = tokens_usage.nb_tokens_by_category.get(TokenCategory.OUTPUT, 0)
    input_non_cached_cost = nb_tokens_input_non_cached * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.INPUT_NON_CACHED,
    )
    input_cached_cost = nb_tokens_input_cached * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.INPUT_CACHED,
    )
    output_cost = nb_tokens_output * model_cost_per_token(
        costs=tokens_usage.unit_costs,
        cost_category=CostCategory.OUTPUT,
    )
    return compute_total_cost(
        input_non_cached_cost=input_non_cached_cost,
        input_cached_cost=input_cached_cost,
        output_cost=output_cost,
    )


def record_unit_priced_usage(*, tokens_usage: TokensUsage, pricing_unit: Literal[PricingUnit.REQUEST, PricingUnit.PAGE], nb_units: int) -> None:
    """Record a call billed by the request or by the page, rather than by the token, on its usage.

    The rates are per million tokens, so each unit is recorded as a million tokens in and out, and the rate table
    prices one unit; the usage says it counts ``pricing_unit``, so a reader of tokens leaves the counts out, the event
    an inference call ends with included, which keeps the call's cost and writes no token counts. Every worker that
    prices this way, a provider's or a plugin's, records its usage through here.

    Args:
        tokens_usage: The usage on the job's report, which the worker base hands to the reporting path.
        pricing_unit: What the provider billed: requests, or pages.
        nb_units: How many requests or pages the call was billed for.
    """
    nb_tokens = nb_units * TOKENS_PER_PRICED_UNIT
    tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: nb_tokens, TokenCategory.OUTPUT: nb_tokens}
    tokens_usage.pricing_unit = pricing_unit
