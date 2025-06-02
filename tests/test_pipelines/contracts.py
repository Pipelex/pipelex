from typing import Any, List, Literal, Optional, Union

from pydantic import Field, model_validator
from typing_extensions import Self, override

from pipelex.types import StrEnum
from pipelex_libraries.pipelines.base_library.questions import BaseAnswer, MultipleChoiceAnswer, SourcedAnswer


class Fees(SourcedAnswer[Any]):
    class Value(StrEnum):
        PERCENTAGE = "Percentage"
        AMOUNT = "Amount"
        INDETERMINATE = "Indeterminate"

    class Currency(StrEnum):
        USD = "USD"
        EUR = "EUR"
        GBP = "GBP"
        AUD = "AUD"
        CAD = "CAD"
        UNKNOWN = "Unknown currency"

    answer: Union[float, BaseAnswer] = Field(
        default=BaseAnswer.INDETERMINATE,
        description="The fee value - for percentages use decimal (e.g. 2.5 for 2.5%), for amounts use the absolute value",
    )
    fee_type: Value = Field(default=Value.PERCENTAGE, description="The type of fee (percentage or amount)")
    fee_currency: Optional[Currency] = Field(
        default=None, description="The currency of the fee amount. Required when fee_type is AMOUNT, should be None for PERCENTAGE"
    )

    @model_validator(mode="after")
    def validate_fee(self) -> Self:
        if isinstance(self.answer, float):
            if self.answer < 0 or self.answer > 100:
                raise ValueError("Fee value must be between 0 and 100")
            if self.fee_type == self.Value.AMOUNT and not self.fee_currency:
                raise ValueError("Currency is required when fee type is AMOUNT")
            if self.fee_type == self.Value.PERCENTAGE and self.fee_currency:
                raise ValueError("Currency should not be set when fee type is PERCENTAGE")
        return self

    @override
    def render_spreadsheet(self) -> str:
        if self.not_applicable:
            return BaseAnswer.NOT_APPLICABLE.value
        elif self.indeterminate:
            return BaseAnswer.INDETERMINATE.value
        if self.fee_type == self.Value.PERCENTAGE:
            return f"{self.answer}"
        else:
            return f"{self.answer} {self.fee_currency.value if self.fee_currency else 'Unknown'}"


class GoverningLaw(SourcedAnswer[Any]):
    """
    The Governing Law can be a country, a state, a city, a law code, etc.
    It should be the name used in the contract.
    """

    answer: Union[str, BaseAnswer] = Field(description="The governing law")


class ContractTypeChoices(StrEnum):
    CONTRACT = "Contract"
    AMENDMENT = "Amendment"


class ContractType(MultipleChoiceAnswer[Literal[ContractTypeChoices.CONTRACT, ContractTypeChoices.AMENDMENT]]):
    """The type of the contract - either a main contract or an amendment."""

    choices: List[str] = Field(
        default=[choice.value for choice in ContractTypeChoices], description="The list of choices for the multiple choice question."
    )
