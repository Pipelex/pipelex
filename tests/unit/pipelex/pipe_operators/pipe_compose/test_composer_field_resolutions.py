"""Unit tests for StructuredContentComposer.field_resolutions.

Verifies that the per-field resolution record built during composition correctly
captures how each field was built: method for every field, plus the rendered
Jinja2 string for template fields. Nested fields record only their method.
"""

from typing import Callable

import pytest
from pydantic import Field

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint, ConstructFieldMethod
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer


class HeadquartersForResolutions(StructuredContent):
    """Inner address used as the target of the NESTED-method test field."""

    street: str = Field(description="Street address rendered from a runtime param")
    city: str = Field(description="City pulled from working memory")


class CustomerForResolutions(StructuredContent):
    """Source object placed in working memory for FROM_VAR / TEMPLATE resolution."""

    customer_name: str = Field(description="Customer name")


class ReportForResolutions(StructuredContent):
    """Output class exercising all four ConstructFieldMethod variants in one composition."""

    title: str = Field(description="Fixed literal")
    customer_name: str = Field(description="Pulled from working memory")
    summary: str = Field(description="Rendered Jinja2 template")
    headquarters: HeadquartersForResolutions = Field(description="Nested sub-construct")


@pytest.mark.asyncio(loop_scope="class")
class TestComposerFieldResolutions:
    @pytest.fixture
    def working_memory_with_inputs(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        load_empty_library()
        customer = CustomerForResolutions(customer_name="Acme Corp")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=customer,
                name="customer",
            ),
        )
        working_memory.add_new_stuff(
            name="city",
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=CustomerForResolutions(customer_name="Paris"),
                name="city",
            ),
        )
        return working_memory

    async def test_field_resolutions_cover_all_methods(self, working_memory_with_inputs: WorkingMemory):
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": "Annual Report",
                "customer_name": {"from": "customer.customer_name"},
                "summary": {"template": "Hello $customer.customer_name"},
                "headquarters": {
                    "street": {"template": "$_street_name"},
                    "city": {"from": "city.customer_name"},
                },
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_inputs,
            output_class=ReportForResolutions,
            runtime_params={"_street_name": "123 Main St"},
        )
        await composer.compose()

        resolutions = composer.field_resolutions
        assert set(resolutions.keys()) == {"title", "customer_name", "summary", "headquarters"}

        assert resolutions["title"] == {"method": ConstructFieldMethod.FIXED}
        assert resolutions["customer_name"] == {"method": ConstructFieldMethod.FROM_VAR}
        assert resolutions["summary"] == {"method": ConstructFieldMethod.TEMPLATE, "rendered": "Hello Acme Corp"}
        assert resolutions["headquarters"] == {"method": ConstructFieldMethod.NESTED}
