from pipelex.types import StrEnum


class ListedConstraint(StrEnum):
    TEMPERATURE_MUST_BE_MULTIPLIED_BY_2 = "temperature_must_be_multiplied_by_2"
    MAX_TOKENS_MUST_BE_HIGH_ENOUGH = "max_tokens_must_be_high_enough"


class ValuedConstraint(StrEnum):
    FIXED_TEMPERATURE = "fixed_temperature"
