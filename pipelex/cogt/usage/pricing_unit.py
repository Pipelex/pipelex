"""What an inference call's usage counts: tokens, or requests or pages priced as tokens.

Rates are per million tokens, so a provider that bills by the request, or an extraction priced by its pages, records
each unit as a million tokens in and out, and the rate table prices one unit. The cost is right, and the counts are not
tokens: a dashboard of tokens must not add them up. The usage says which it holds in its ``pricing_unit`` so a reader
of the counts can tell them apart. Today one reader does, the event an inference call ends with, which keeps the cost
and leaves the token counts off. The run's cost table and the run graph's usage still add a unit-priced call's counts
to their token totals, and the client-facing ``TokensUsageRecord`` still carries them as tokens.
"""

from enum import StrEnum

#: How many tokens one request or one page is recorded as, so a rate per million tokens prices one unit.
TOKENS_PER_PRICED_UNIT = 1_000_000


class PricingUnit(StrEnum):
    """What a usage's ``nb_tokens_by_category`` counts."""

    TOKEN = "token"
    REQUEST = "request"
    PAGE = "page"

    @property
    def counts_tokens(self) -> bool:
        """Whether the counts are tokens the provider read and wrote, rather than requests or pages priced as tokens."""
        match self:
            case PricingUnit.TOKEN:
                return True
            case PricingUnit.REQUEST | PricingUnit.PAGE:
                return False
