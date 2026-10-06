from enum import StrEnum


class ListedConstraint(StrEnum):
    TEMPERATURE_MUST_BE_MULTIPLIED_BY_2 = "temperature_must_be_multiplied_by_2"
    TEMPERATURE_UNSUPPORTED = "temperature_unsupported"
    MAX_TOKENS_MUST_BE_HIGH_ENOUGH = "max_tokens_must_be_high_enough"
    # The model always thinks: its provider refuses a request that turns thinking off
    THINKING_CANNOT_BE_DISABLED = "thinking_cannot_be_disabled"


class ValuedConstraint(StrEnum):
    FIXED_TEMPERATURE = "fixed_temperature"
    # The bounds of the manual thinking budget the provider accepts for the model, both inclusive
    MIN_THINKING_BUDGET = "min_thinking_budget"
    MAX_THINKING_BUDGET = "max_thinking_budget"
