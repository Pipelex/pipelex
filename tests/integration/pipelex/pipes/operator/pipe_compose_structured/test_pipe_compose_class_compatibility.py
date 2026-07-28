"""Integration tests for PipeCompose class compatibility scenarios.

These tests verify tricky cases involving:
- Subclassing: TextContent subclasses, StructuredContent subclasses in lists
- Class equivalence: structurally identical classes being converted
- Item type conversions in lists: subclass items, equivalent items
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.models_for_pipe_compose import (
    DiscountedProduct,
    Employee,
    Manager,
    Product,
    RichTextContent,
)
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import ClassCompatibilityTestData


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeClassCompatibility:
    """Integration tests for class compatibility scenarios in PipeCompose."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    async def test_subclass_to_base_text_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that TextContent subclass is accepted when field expects base TextContent."""
        load_test_library(test_library_path)

        # Create working memory with RichTextContent (subclass of TextContent)
        rich_text = RichTextContent(text="Bold and italic text", bold=True, italic=True)
        rich_text_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=rich_text,
            name="rich_text",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="rich_text", stuff=rich_text_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose report with base TextContent field from subclass",
                "inputs": {"rich_text": "Text"},
                "construct": ClassCompatibilityTestData.SUBCLASS_TO_BASE_CONSTRUCT,
                "output": "compose_structured_test.ReportWithBaseTextContent",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_subclass_to_base",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "ReportWithBaseTextContent"

        report = main_stuff.content
        # The content field is TextContent, subclass RichTextContent should be accepted
        assert isinstance(report.content, TextContent)  # type: ignore[attr-defined]
        assert report.content.text == "Bold and italic text"  # type: ignore[attr-defined]
        # Subclass-specific fields should be preserved
        assert hasattr(report.content, "bold")  # type: ignore[attr-defined]
        assert report.content.bold is True  # type: ignore[attr-defined]
        assert report.note == "Testing subclass to base conversion"  # type: ignore[attr-defined]

        pretty_print(report, title="ReportWithBaseTextContent - RichTextContent to TextContent")

    async def test_equivalent_class_list_items(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that structurally equivalent class items are converted in list[X]."""
        load_test_library(test_library_path)

        # Create working memory with ListContent[Employee]
        # Employee has same fields as Person (name, role) - structurally equivalent
        employees = ListContent[Employee](
            items=[
                Employee(name="Alice", role="Engineer"),
                Employee(name="Bob", role="Designer"),
            ]
        )
        employees_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=employees,
            name="employees",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="employees", stuff=employees_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose team with list[Person] from structurally equivalent Employee items",
                "inputs": {"employees": "Text"},
                "construct": ClassCompatibilityTestData.EQUIVALENT_LIST_ITEMS_CONSTRUCT,
                "output": "compose_structured_test.TeamWithPersons",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_equivalent_items",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "TeamWithPersons"

        team = main_stuff.content
        # The members field is list[Person], Employee items should be converted
        assert isinstance(team.members, list)  # type: ignore[attr-defined]
        assert len(team.members) == 2  # type: ignore[attr-defined]
        # Items should now be Person instances (rebuilt from Employee dicts)
        assert type(team.members[0]).__name__ == "Person"  # type: ignore[attr-defined]
        assert team.members[0].name == "Alice"  # type: ignore[attr-defined]
        assert team.members[1].role == "Designer"  # type: ignore[attr-defined]
        assert team.team_name == "Equivalent Team"  # type: ignore[attr-defined]

        pretty_print(team, title="TeamWithPersons - Employee items to Person list")

    async def test_subclass_list_items(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that subclass items are accepted when list expects base class."""
        load_test_library(test_library_path)

        # Create working memory with ListContent[Manager]
        # Manager is a subclass of Person
        managers = ListContent[Manager](
            items=[
                Manager(name="Carol", role="Director", department="Engineering"),
                Manager(name="Dave", role="Lead", department="Design"),
            ]
        )
        managers_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=managers,
            name="managers",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="managers", stuff=managers_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose team with list[Person] from Manager subclass items",
                "inputs": {"managers": "Text"},
                "construct": ClassCompatibilityTestData.SUBCLASS_LIST_ITEMS_CONSTRUCT,
                "output": "compose_structured_test.TeamWithPersons",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_subclass_items",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "TeamWithPersons"

        team = main_stuff.content
        # The members field is list[Person], Manager subclass items should be accepted
        assert isinstance(team.members, list)  # type: ignore[attr-defined]
        assert len(team.members) == 2  # type: ignore[attr-defined]
        # Items are rebuilt as Person (base class) from Manager dicts
        assert team.members[0].name == "Carol"  # type: ignore[attr-defined]
        assert team.members[1].role == "Lead"  # type: ignore[attr-defined]
        assert team.team_name == "Manager Team"  # type: ignore[attr-defined]

        pretty_print(team, title="TeamWithPersons - Manager items to Person list")

    async def test_subclass_list_content_items(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that subclass items are accepted when ListContent expects base class."""
        load_test_library(test_library_path)

        # Create working memory with ListContent[Manager]
        managers = ListContent[Manager](
            items=[
                Manager(name="Eve", role="VP", department="Operations"),
                Manager(name="Frank", role="Head", department="Sales"),
            ]
        )
        managers_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=managers,
            name="managers_list",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="managers_list", stuff=managers_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose team with ListContent[Person] from Manager subclass items",
                "inputs": {"managers_list": "Text"},
                "construct": ClassCompatibilityTestData.SUBCLASS_LIST_CONTENT_ITEMS_CONSTRUCT,
                "output": "compose_structured_test.TeamWithListContentPersons",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_subclass_list_content_items",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "TeamWithListContentPersons"

        team = main_stuff.content
        # The members field is ListContent[Person], Manager items should be kept as objects
        assert isinstance(team.members, ListContent)  # type: ignore[attr-defined]
        assert team.members.nb_items == 2  # type: ignore[attr-defined]
        # Items should be Person objects (subclass Manager is compatible)
        assert team.members.items[0].name == "Eve"  # type: ignore[attr-defined]
        assert team.members.items[1].role == "Head"  # type: ignore[attr-defined]
        assert team.team_name == "ListContent Manager Team"  # type: ignore[attr-defined]

        pretty_print(team, title="TeamWithListContentPersons - Manager items to ListContent[Person]")

    async def test_mixed_subclass_items_in_list(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that mixed base and subclass items are accepted in list[BaseClass]."""
        load_test_library(test_library_path)

        # Create working memory with ListContent containing both Product and DiscountedProduct
        mixed_products = ListContent[Product](
            items=[
                Product(sku="SKU001", price=99.99),
                DiscountedProduct(sku="SKU002", price=149.99, discount_percent=20.0),
                Product(sku="SKU003", price=49.99),
            ]
        )
        products_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=mixed_products,
            name="mixed_products",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="mixed_products", stuff=products_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose catalog with list[Product] from mixed Product and DiscountedProduct items",
                "inputs": {"mixed_products": "Text"},
                "construct": ClassCompatibilityTestData.MIXED_SUBCLASS_ITEMS_CONSTRUCT,
                "output": "compose_structured_test.Catalog",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_mixed_subclass_items",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "Catalog"

        catalog = main_stuff.content
        # The products field is list[Product], both Product and DiscountedProduct should be accepted
        assert isinstance(catalog.products, list)  # type: ignore[attr-defined]
        assert len(catalog.products) == 3  # type: ignore[attr-defined]
        assert catalog.products[0].sku == "SKU001"  # type: ignore[attr-defined]
        assert catalog.products[0].price == 99.99  # type: ignore[attr-defined]
        assert catalog.products[1].sku == "SKU002"  # type: ignore[attr-defined]
        assert catalog.products[2].price == 49.99  # type: ignore[attr-defined]
        assert catalog.catalog_name == "Mixed Products Catalog"  # type: ignore[attr-defined]

        pretty_print(catalog, title="Catalog - Mixed Product/DiscountedProduct items")
