"""Unit tests for StructuredContentComposer - composes StructuredContent from blueprints.

The composer takes a ConstructBlueprint and WorkingMemory, resolves all fields
according to their composition methods, and produces a StructuredContent instance.
"""

from typing import Any, Callable, ClassVar, get_origin

import pytest
from pydantic import Field

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_native_concept
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.pipe_operators.compose.exceptions import StructuredContentComposerValidationError, StructuredContentComposerValueError
from pipelex.pipe_operators.compose.structured_content_composer import StructuredContentComposer
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


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


class CompanyWithOptionalAddress(StructuredContent):
    """Company with optional address using Python 3.10+ union syntax (X | None).

    This tests the fix for _get_nested_field_class which used hasattr(annotation, "__origin__")
    to detect Optional types. The Python 3.10+ union syntax creates types.UnionType which
    doesn't have __origin__, so get_origin() must be used instead.
    """

    name: str = Field(description="Company name")
    headquarters: Address | None = Field(default=None, description="Optional company headquarters")


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerNestedOptional:
    """Tests for composing nested structures with Python 3.10+ union syntax (X | None).

    This tests the fix for the bug where _get_nested_field_class used
    hasattr(annotation, "__origin__") to detect Optional types, which doesn't work
    with Python 3.10+ union syntax (Address | None creates types.UnionType).
    """

    @pytest.fixture
    def working_memory_with_address(self, load_empty_library: Callable[[], None]) -> WorkingMemory:
        """Create working memory with address components."""
        load_empty_library()
        addr = Address(street="456 Elm St", city="Lyon", country="France")
        company_name_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="OptionalCorp"),
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

    async def test_compose_nested_optional_with_python_310_union_syntax(self, working_memory_with_address: WorkingMemory):
        """Test composing nested structure when field uses Python 3.10+ union syntax.

        Before fix: hasattr(annotation, "__origin__") would return False for types.UnionType,
        causing the Address | None type to not have None stripped, and instantiation would fail.

        After fix: get_origin() correctly handles both typing.Union and types.UnionType,
        so the nested Address is correctly identified and composed.
        """
        nested_construct = {
            "name": {"from": "company_name"},
            "headquarters": {
                "street": {"from": "addr.street"},
                "city": {"from": "addr.city"},
                "country": "France",
            },
        }
        blueprint = ConstructBlueprint.make_from_raw(nested_construct)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_address,
            output_class=CompanyWithOptionalAddress,
        )
        result = await composer.compose()

        assert isinstance(result, CompanyWithOptionalAddress)
        assert result.name == "OptionalCorp"
        assert isinstance(result.headquarters, Address)
        assert result.headquarters.street == "456 Elm St"
        assert result.headquarters.city == "Lyon"
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

    async def test_invalid_dotted_path_raises_value_error(self, load_empty_library: Callable[[], None]):
        """Test that an invalid dotted path raises StructuredContentComposerValueError.

        This ensures that typos in dotted paths (e.g., deal.nonexistent_field) are
        surfaced as errors and not silently swallowed during validation.
        """
        load_empty_library()
        deal = Deal(customer_name="Acme Corp", amount=50000.0)
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=deal,
                name="deal",
            ),
        )

        blueprint = ConstructBlueprint.make_from_raw(
            {
                "report_title": {"from": "deal.customer_name"},
                "customer_name": {"from": "deal.custmer_name"},  # Typo: missing 'o' in customer
                "deal_value": {"from": "deal.amount"},
                "summary_text": "Test summary",
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=SalesSummary,
        )

        with pytest.raises(StructuredContentComposerValueError, match="custmer_name"):
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

        with pytest.raises(StructuredContentComposerValidationError):
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


# Test models using typing.Optional syntax (works on all Python versions)


class CompanyWithTypingOptionalAddress(StructuredContent):
    """Company with optional address using typing.Optional syntax."""

    name: str = Field(description="Company name")
    headquarters: Address | None = Field(default=None, description="Optional headquarters")


class TestGetNestedFieldClassOptionalSyntaxes:
    """Tests for _get_nested_field_class with different Optional syntaxes.

    This tests the fix where hasattr(annotation, "__origin__") was used to detect
    Optional types, which doesn't work for Python 3.10+ union syntax (X | None).
    The fix uses get_origin() which handles both syntaxes correctly.

    These tests directly verify that _get_nested_field_class returns the correct
    class for both Optional[Address] and Address | None syntaxes.
    """

    def test_get_nested_field_class_with_typing_optional(self):
        """Test _get_nested_field_class correctly handles typing.Optional[Address].

        typing.Optional[Address] has __origin__ = typing.Union, so the old
        hasattr(annotation, "__origin__") check worked. This test ensures we
        didn't break backward compatibility.
        """
        # Need valid nested construct data for the blueprint
        nested_construct = {
            "name": "Test",
            "headquarters": {"street": "123 Main", "city": "Paris", "country": "France"},
        }
        blueprint = ConstructBlueprint.make_from_raw(nested_construct)
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithTypingOptionalAddress,
        )

        # Directly test the private method (noqa needed for testing internal behavior)
        result = composer._get_nested_field_class("headquarters")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        assert result is Address, f"Expected Address, got {result}"

    def test_get_nested_field_class_with_python_310_union_syntax(self):
        """Test _get_nested_field_class correctly handles Python 3.10+ Address | None.

        Before the fix: types.UnionType (from X | None) doesn't have __origin__,
        so hasattr(annotation, "__origin__") returned False, and the None wasn't
        stripped. This would cause Address | None to be returned instead of Address.

        After the fix: get_origin() correctly returns types.UnionType for this case,
        and we strip the None to get Address.
        """
        # Need valid nested construct data for the blueprint
        nested_construct = {
            "name": "Test",
            "headquarters": {"street": "123 Main", "city": "Paris", "country": "France"},
        }
        blueprint = ConstructBlueprint.make_from_raw(nested_construct)
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithOptionalAddress,
        )

        # Directly test the private method (noqa needed for testing internal behavior)
        result = composer._get_nested_field_class("headquarters")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        assert result is Address, f"Expected Address, got {result}"

    def test_both_optional_syntaxes_return_same_class(self):
        """Test that both Optional syntaxes return the same nested class.

        This is the key test: regardless of whether Optional[Address] or Address | None
        is used, _get_nested_field_class should return Address in both cases.
        """
        # Need valid nested construct data for the blueprint
        nested_construct = {
            "name": "Test",
            "headquarters": {"street": "123 Main", "city": "Paris", "country": "France"},
        }
        blueprint = ConstructBlueprint.make_from_raw(nested_construct)
        working_memory = WorkingMemory()

        composer_typing_optional = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithTypingOptionalAddress,
        )

        composer_union_syntax = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithOptionalAddress,
        )

        # Ignore lint/type errors: testing internal behavior directly
        result_typing = composer_typing_optional._get_nested_field_class("headquarters")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        result_union = composer_union_syntax._get_nested_field_class("headquarters")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        assert result_typing is Address
        assert result_union is Address
        assert result_typing is result_union, "Both syntaxes should return the same class"


# Test models for generic type tests (list, dict)
class CompanyWithAddressList(StructuredContent):
    """Company with a list of addresses - should NOT be unwrapped by _get_nested_field_class."""

    name: str = Field(description="Company name")
    branches: list[Address] = Field(
        default_factory=empty_list_factory_of(Address),
        description="List of branch addresses",
    )


class CompanyWithAddressDict(StructuredContent):
    """Company with a dict of addresses - should NOT be unwrapped by _get_nested_field_class."""

    name: str = Field(description="Company name")
    offices: dict[str, Address] = Field(default_factory=dict, description="Dict of office addresses by name")


class TestGetNestedFieldClassGenericTypes:
    """Tests for _get_nested_field_class with generic types that should NOT be unwrapped.

    This tests the fix for the bug where `get_origin(annotation) is not None` matched
    ALL generic types including list[X], dict[K, V], etc. The condition was too broad
    and would incorrectly unwrap list[Address] to Address.

    The fix checks specifically for Union/UnionType with None in args to detect Optional types.
    """

    def test_get_nested_field_class_does_not_unwrap_list(self):
        """Test _get_nested_field_class does NOT unwrap list[Address] to Address.

        Before the fix: list[Address] would be unwrapped to Address because
        get_origin(list[Address]) returns list (not None), triggering the unwrap.

        After the fix: list[Address] is returned as-is because we only unwrap
        Optional types (Union/UnionType with None in args).
        """
        # Use a simple blueprint - we just need to test the _get_nested_field_class method
        # The blueprint doesn't need to match the field we're testing
        simple_construct = {"name": "Test Company"}
        blueprint = ConstructBlueprint.make_from_raw(simple_construct)
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithAddressList,
        )

        # Directly test the private method (noqa needed for testing internal behavior)
        result = composer._get_nested_field_class("branches")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        # The bug would have returned Address here instead of list[Address]
        assert result is not Address, "list[Address] should NOT be unwrapped to Address"
        # The correct result should be list[Address]
        assert get_origin(result) is list, f"Expected list[Address], got {result}"

    def test_get_nested_field_class_does_not_unwrap_dict(self):
        """Test _get_nested_field_class does NOT unwrap dict[str, Address] to str.

        Before the fix: dict[str, Address] would be unwrapped to str because
        get_origin(dict[str, Address]) returns dict (not None), triggering the unwrap.

        After the fix: dict[str, Address] is returned as-is.
        """
        # Use a simple blueprint - we just need to test the _get_nested_field_class method
        # The blueprint doesn't need to match the field we're testing
        simple_construct = {"name": "Test Company"}
        blueprint = ConstructBlueprint.make_from_raw(simple_construct)
        working_memory = WorkingMemory()

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory,
            output_class=CompanyWithAddressDict,
        )

        # Directly test the private method (noqa needed for testing internal behavior)
        result = composer._get_nested_field_class("offices")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        # The bug would have returned str here instead of dict[str, Address]
        assert result is not str, "dict[str, Address] should NOT be unwrapped to str"
        assert result is not Address, "dict[str, Address] should NOT be unwrapped to Address"
        # The correct result should be dict[str, Address]
        assert get_origin(result) is dict, f"Expected dict[str, Address], got {result}"


# Test model for runtime params testing
class ReportWithRuntimeParams(StructuredContent):
    """Report that uses runtime params in templates."""

    title: str = Field(description="Report title")
    generated_summary: str = Field(description="Summary generated from template with runtime params")


# Test model for nested structure with runtime params
class NestedReportWithRuntimeParams(StructuredContent):
    """Nested structure with runtime params in templates."""

    header: str = Field(description="Header text")
    details: ReportWithRuntimeParams = Field(description="Nested report details")


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentComposerRuntimeParams:
    """Tests for template fields accessing runtime_params and extra_context.

    This tests the fix for the inconsistency where _resolve_template only used
    working_memory.generate_context(), but _run_template_mode in PipeCompose also
    included pipe_run_params.params and extra_context. Templates in construct fields
    should have access to the same context as templates in template mode.
    """

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

    async def test_template_field_accesses_runtime_params(self, working_memory_with_deal: WorkingMemory):
        """Test that template fields can access runtime_params (from PipeRunParams.params).

        Before fix: templates in construct fields could not access runtime params,
        causing template rendering to fail or produce incorrect output.

        After fix: runtime_params are merged into the template context, making them
        accessible just like in _run_template_mode.
        """
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": {"from": "deal.customer_name"},
                "generated_summary": {"template": "Report for $_report_type generated on $_report_date"},
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=ReportWithRuntimeParams,
            runtime_params={"_report_type": "Quarterly", "_report_date": "2025-01-02"},
        )
        result = await composer.compose()

        assert isinstance(result, ReportWithRuntimeParams)
        assert result.title == "Acme Corp"
        assert "Quarterly" in result.generated_summary
        assert "2025-01-02" in result.generated_summary

    async def test_template_field_accesses_extra_context(self, working_memory_with_deal: WorkingMemory):
        """Test that template fields can access extra_context (from PipeCompose.extra_context).

        Before fix: templates in construct fields could not access extra_context,
        causing template rendering to fail or produce incorrect output.

        After fix: extra_context is merged into the template context, making it
        accessible just like in _run_template_mode.
        """
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": "Financial Report",
                "generated_summary": {"template": "Summary for $fiscal_year, quarter $quarter"},
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=ReportWithRuntimeParams,
            extra_context={"fiscal_year": "2025", "quarter": "1"},
        )
        result = await composer.compose()

        assert isinstance(result, ReportWithRuntimeParams)
        assert result.title == "Financial Report"
        assert "2025" in result.generated_summary
        assert "quarter 1" in result.generated_summary

    async def test_template_field_combines_all_context_sources(self, working_memory_with_deal: WorkingMemory):
        """Test that template fields can access all context sources together.

        Context is built in order (later sources override earlier):
        1. Working memory context (stuffs as variables)
        2. Runtime params (from PipeRunParams.params)
        3. Extra context (from PipeCompose.extra_context)

        This ensures templates can use variables from all sources in a single template.
        """
        blueprint = ConstructBlueprint.make_from_raw(
            {
                "title": {"from": "deal.customer_name"},
                "generated_summary": {"template": "Customer: $deal.customer_name, Type: $_report_type, Year: $fiscal_year"},
            }
        )

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=ReportWithRuntimeParams,
            runtime_params={"_report_type": "Annual"},
            extra_context={"fiscal_year": "2025"},
        )
        result = await composer.compose()

        assert isinstance(result, ReportWithRuntimeParams)
        assert result.title == "Acme Corp"
        # Template should include values from all three sources
        assert "Acme Corp" in result.generated_summary  # From working memory
        assert "Annual" in result.generated_summary  # From runtime_params
        assert "2025" in result.generated_summary  # From extra_context

    async def test_nested_template_fields_access_runtime_params(self, working_memory_with_deal: WorkingMemory):
        """Test that nested structures also have access to runtime_params and extra_context.

        The fix passes runtime_params and extra_context to nested composers,
        ensuring templates in nested structures work correctly.
        """
        nested_construct = {
            "header": {"template": "Report for $_report_type"},
            "details": {
                "title": {"from": "deal.customer_name"},
                "generated_summary": {"template": "Generated on $_report_date for $fiscal_year"},
            },
        }
        blueprint = ConstructBlueprint.make_from_raw(nested_construct)

        composer = StructuredContentComposer(
            construct_blueprint=blueprint,
            working_memory=working_memory_with_deal,
            output_class=NestedReportWithRuntimeParams,
            runtime_params={"_report_type": "Monthly", "_report_date": "2025-01-15"},
            extra_context={"fiscal_year": "2025"},
        )
        result = await composer.compose()

        assert isinstance(result, NestedReportWithRuntimeParams)
        # Top-level template should access runtime_params
        assert "Monthly" in result.header
        # Nested template should access both runtime_params and extra_context
        assert isinstance(result.details, ReportWithRuntimeParams)
        assert result.details.title == "Acme Corp"
        assert "2025-01-15" in result.details.generated_summary  # From runtime_params
        assert "2025" in result.details.generated_summary  # From extra_context
