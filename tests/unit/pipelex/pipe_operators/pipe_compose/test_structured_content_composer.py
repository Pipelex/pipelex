"""Unit tests for StructuredContentComposer - composes StructuredContent from blueprints.

The composer takes a ConstructBlueprint and WorkingMemory, resolves all fields
according to their composition methods, and produces a StructuredContent instance.
"""

from typing import Any, Callable, ClassVar

import pytest
from pydantic import Field, ValidationError

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer


# Test StructuredContent classes for testing
class SimpleReport(StructuredContent):
    """Simple report for testing fixed values and variable references."""

    title: str = Field(description="Report title")
    author: str = Field(description="Author name")
    score: float = Field(description="Report score")
    is_draft: bool = Field(default=False, description="Whether this is a draft")


class Address(StructuredContent):
    """Address for nested structure testing."""

    street: str = Field(description="Street address")
    city: str = Field(description="City name")
    country: str = Field(description="Country name")


class Company(StructuredContent):
    """Company with nested address for testing nested composition."""

    name: str = Field(description="Company name")
    headquarters: Address = Field(description="Company headquarters")


class Deal(StructuredContent):
    """Deal for working memory input testing."""

    customer_name: str = Field(description="Customer name")
    amount: float = Field(description="Deal amount")


class SalesSummary(StructuredContent):
    """Sales summary for template testing."""

    report_title: str = Field(description="Title of the report")
    customer_name: str = Field(description="Customer name")
    deal_value: float = Field(description="Deal value")
    summary_text: str = Field(description="Generated summary text")


class ComposerTestData:
    """Test data for StructuredContentComposer tests."""

    # Fixed values only
    FIXED_ONLY_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "title": "Annual Report",
        "author": "John Doe",
        "score": 95.5,
        "is_draft": False,
    }

    # Variable references only
    VAR_REF_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "report_title": {"from": "deal.customer_name"},
        "customer_name": {"from": "deal.customer_name"},
        "deal_value": {"from": "deal.amount"},
        "summary_text": {"from": "deal.customer_name"},
    }

    # Mixed: fixed + variable refs
    MIXED_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "report_title": "Monthly Sales Report",
        "customer_name": {"from": "deal.customer_name"},
        "deal_value": {"from": "deal.amount"},
        "summary_text": {"template": "Deal worth $deal.amount with $deal.customer_name"},
    }

    # Nested construct
    NESTED_CONSTRUCT: ClassVar[dict[str, Any]] = {
        "name": {"from": "company_name"},
        "headquarters": {
            "street": {"from": "addr.street"},
            "city": {"from": "addr.city"},
            "country": "France",
        },
    }


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerFixedValues:
    """Tests for composing with fixed values only."""

    async def test_compose_all_fixed_values(self):
        """Test composing a StructuredContent with all fixed values."""
        blueprint = ConstructBlueprint.make_from_raw(ComposerTestData.FIXED_ONLY_CONSTRUCT)
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=SimpleReport,
        )
        result = await composer.compose()

        assert isinstance(result, SimpleReport)
        assert result.title == "Annual Report"
        assert result.author == "John Doe"
        assert result.score == 95.5
        assert result.is_draft is False


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerVariableRefs:
    """Tests for composing with variable references."""

    @pytest.fixture
    def working_memory_with_deal(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with a Deal object."""
        load_empty_library()
        deal = Deal(customer_name="Acme Corp", amount=50000.0)
        return WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),  # Using native concept for simplicity
                content=deal,
                name="deal",
            ),
        )

    async def test_compose_with_variable_refs(self, working_memory_with_deal: WorkingMemory):
        """Test composing with variable references from working memory."""
        blueprint = ConstructBlueprint.make_from_raw(ComposerTestData.VAR_REF_CONSTRUCT)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=SalesSummary,
        )
        result = await composer.compose()

        assert isinstance(result, SalesSummary)
        assert result.customer_name == "Acme Corp"
        assert result.deal_value == 50000.0


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerTemplates:
    """Tests for composing with templates."""

    @pytest.fixture
    def working_memory_with_deal(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with a Deal object."""
        load_empty_library()
        deal = Deal(customer_name="Acme Corp", amount=50000.0)
        return WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=deal,
                name="deal",
            ),
        )

    async def test_compose_with_template(self, working_memory_with_deal: WorkingMemory):
        """Test composing with a template field."""
        blueprint = ConstructBlueprint.make_from_raw(ComposerTestData.MIXED_CONSTRUCT)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=SalesSummary,
        )
        result = await composer.compose()

        assert isinstance(result, SalesSummary)
        assert result.report_title == "Monthly Sales Report"
        assert result.customer_name == "Acme Corp"
        assert result.deal_value == 50000.0
        # Template should render the variables
        assert "50000.0" in result.summary_text
        assert "Acme Corp" in result.summary_text


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerNested:
    """Tests for composing nested structures."""

    @pytest.fixture
    def working_memory_with_address(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with address components."""
        load_empty_library()
        addr = Address(street="123 Main St", city="Paris", country="France")
        company_name_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="TechCorp"),
            name="company_name",
        )
        addr_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=addr,
            name="addr",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="company_name", stuff=company_name_stuff)
        working_memory.add_new_stuff(name="addr", stuff=addr_stuff)
        return working_memory

    async def test_compose_nested_structure(self, working_memory_with_address: WorkingMemory):
        """Test composing a StructuredContent with nested structure."""
        blueprint = ConstructBlueprint.make_from_raw(ComposerTestData.NESTED_CONSTRUCT)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_address,
            output_class=Company,
        )
        result = await composer.compose()

        assert isinstance(result, Company)
        assert result.name == "TechCorp"
        assert isinstance(result.headquarters, Address)
        assert result.headquarters.street == "123 Main St"
        assert result.headquarters.city == "Paris"
        assert result.headquarters.country == "France"


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerErrors:
    """Tests for error handling in the composer."""

    async def test_missing_variable_raises_error(self, load_empty_library: Callable[[], None]):
        """Test that referencing a missing variable raises an appropriate error."""
        load_empty_library()
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": {"from": "nonexistent.variable"},
                "author": "Test",
                "score": 1.0,
            }
        )
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=SimpleReport,
        )

        with pytest.raises(WorkingMemoryStuffNotFoundError):
            await composer.compose()

    async def test_type_mismatch_raises_error(self, load_empty_library: Callable[[], None]):
        """Test that type mismatch between blueprint and class raises error."""
        load_empty_library()
        # score should be float but we provide a string that can't be converted
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": "Test Report",
                "author": "Test Author",
                "score": "not a number",  # This should cause validation error
            }
        )
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=SimpleReport,
        )

        with pytest.raises(ValidationError):
            await composer.compose()


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerWithTemplates:
    """Tests for async composition (templates may require async rendering)."""

    @pytest.fixture
    def working_memory_with_deal(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with a Deal object."""
        load_empty_library()
        deal = Deal(customer_name="Acme Corp", amount=50000.0)
        return WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=deal,
                name="deal",
            ),
        )

    async def test_compose_with_templates(self, working_memory_with_deal: WorkingMemory):
        """Test async composition when templates are involved."""
        blueprint = ConstructBlueprint.make_from_raw(ComposerTestData.MIXED_CONSTRUCT)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=SalesSummary,
        )
        result = await composer.compose()

        assert isinstance(result, SalesSummary)
        assert "50000.0" in result.summary_text or "50000" in result.summary_text
        assert "Acme Corp" in result.summary_text


# Additional test models for dotted path type conversion
class ContainerWithTextContent(StructuredContent):
    """Container that holds a TextContent for testing dotted path type conversion."""

    content: TextContent = Field(description="Text content")
    label: str = Field(description="Label")


class OutputWithStringField(StructuredContent):
    """Output that expects a string field from a dotted path to TextContent."""

    extracted_text: str = Field(description="Text extracted from dotted path")
    description: str = Field(description="Description")


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerDottedPathTypeConversion:
    """Tests for type conversion when using dotted paths.

    This tests the fix for the bug where dotted paths did not apply type conversion:
    - Non-dotted path `{ from = "content" }` correctly converted TextContent -> str
    - Dotted path `{ from = "obj.content" }` returned raw TextContent, causing Pydantic error

    After the fix, both paths should consistently apply type conversion.
    """

    @pytest.fixture
    def working_memory_with_container(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with a container holding TextContent."""
        load_empty_library()
        container = ContainerWithTextContent(
            content=TextContent(text="Hello from TextContent"),
            label="test-container",
        )
        return WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=container,
                name="container",
            ),
        )

    async def test_dotted_path_converts_text_content_to_str(self, working_memory_with_container: WorkingMemory):
        """Test that dotted path to TextContent is converted to str when target field expects str.

        This tests the fix: before the fix, `{ from = "container.content" }` would return
        the raw TextContent object, causing a Pydantic validation error.
        After the fix, it should correctly extract TextContent.text as str.
        """
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "extracted_text": {"from": "container.content"},  # TextContent -> str conversion needed
                "description": "Test description",
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_container,
            output_class=OutputWithStringField,
        )
        result = await composer.compose()

        assert isinstance(result, OutputWithStringField)
        assert result.extracted_text == "Hello from TextContent"
        assert result.description == "Test description"

    async def test_dotted_path_preserves_text_content_when_expected(self, working_memory_with_container: WorkingMemory):
        """Test that dotted path to TextContent is preserved when target field expects TextContent."""

        class OutputWithTextContentField(StructuredContent):
            content: TextContent = Field(description="Text content object")
            label: str = Field(description="Label")

        blueprint = ConstructBlueprint.make_from_raw(
            {
                "content": {"from": "container.content"},  # TextContent -> TextContent, no conversion
                "label": {"from": "container.label"},
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_container,
            output_class=OutputWithTextContentField,
        )
        result = await composer.compose()

        assert isinstance(result, OutputWithTextContentField)
        assert isinstance(result.content, TextContent)
        assert result.content.text == "Hello from TextContent"
        assert result.label == "test-container"
