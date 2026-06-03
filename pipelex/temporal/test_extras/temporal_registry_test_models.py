from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from pipelex.system.registries.registry_base import ModelType, RegistryModels
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


# for testing & examples
class Person(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    age: int
    job: str


class FixtureLineItem(BaseModel):
    """Inner-most leaf type of FixtureInvoice. Designed to exercise type preservation
    across the Temporal data-converter boundary for ``act_llm_gen_object`` /
    ``act_llm_gen_object_list``. Named ``Fixture*`` (not ``Test*``) so pytest
    does not try to collect it as a test class.
    """

    product_name: str
    quantity: int
    unit_price: float


class FixtureCustomer(BaseModel):
    name: str
    email: str


class FixtureInvoice(BaseModel):
    """Test-only nested structure used to validate that ``make_object`` /
    ``make_object_list`` preserves nested fields through the cross-process
    JSON round-trip (``model_dump(mode="json", serialize_as_any=True)`` →
    Temporal data converter → ``model_validate(...)``).
    """

    invoice_number: str
    customer: FixtureCustomer
    line_items: list[FixtureLineItem] = Field(default_factory=empty_list_factory_of(FixtureLineItem))
    total_amount: float


class TemporalTestModels(RegistryModels):
    TEST_MODELS: ClassVar[list[ModelType]] = [Person, FixtureCustomer, FixtureLineItem, FixtureInvoice]
