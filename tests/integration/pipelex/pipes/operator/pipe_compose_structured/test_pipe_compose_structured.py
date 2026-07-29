"""Integration tests for PipeCompose with construct (StructuredContent output).

These tests verify that PipeCompose can produce StructuredContent objects
using the construct blueprint syntax in MTHDS files.
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.models_for_pipe_compose import (
    Address,
    Deal,
)
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import ComposeStructuredTestData


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeStructured:
    """Integration tests for PipeCompose with construct."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    async def test_compose_fixed_values_only(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test PipeCompose with construct containing only fixed values."""
        load_test_library(test_library_path)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose a simple report with fixed values",
                "construct": ComposeStructuredTestData.FIXED_ONLY_CONSTRUCT,
                "output": "compose_structured_test.SimpleReport",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_fixed_values",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        # Check type by class name since auto-generated classes have different identity
        assert type(main_stuff.content).__name__ == "SimpleReport"

        report = main_stuff.content
        assert report.title == "Annual Report"  # type: ignore[attr-defined]
        assert report.author == "John Doe"  # type: ignore[attr-defined]
        assert report.score == 95.5  # type: ignore[attr-defined]

        pretty_print(report, title="SimpleReport with fixed values")

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

    async def test_compose_with_variable_refs_and_templates(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test PipeCompose with construct containing variable refs and templates."""
        load_test_library(test_library_path)

        # Create working memory with Deal
        deal = Deal(customer_name="Acme Corp", amount=50000.0)
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=deal,
                name="deal",
            ),
        )

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose a sales summary from deal data",
                "inputs": {"deal": "Text"},
                "construct": ComposeStructuredTestData.MIXED_CONSTRUCT,
                "output": "compose_structured_test.SalesSummary",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_sales_summary",
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
        # Check type by class name since auto-generated classes have different identity
        assert type(main_stuff.content).__name__ == "SalesSummary"

        summary = main_stuff.content
        assert summary.report_title == "Monthly Sales Report"  # type: ignore[attr-defined]
        assert summary.customer_name == "Acme Corp"  # type: ignore[attr-defined]
        assert summary.deal_value == 50000.0  # type: ignore[attr-defined]
        assert "50000" in summary.summary_text or "50000.0" in summary.summary_text  # type: ignore[attr-defined]
        assert "Acme Corp" in summary.summary_text  # type: ignore[attr-defined]

        pretty_print(summary, title="SalesSummary with mixed construct")

    async def test_compose_with_nested_structure(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test PipeCompose with construct containing nested structures."""
        load_test_library(test_library_path)

        # Create working memory with address and company name
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

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose a company with nested address",
                "inputs": {"company_name": "Text", "addr": "Text"},
                "construct": ComposeStructuredTestData.NESTED_CONSTRUCT,
                "output": "compose_structured_test.Company",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_company",
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
        # Check type by class name since auto-generated classes have different identity
        assert type(main_stuff.content).__name__ == "Company"

        company = main_stuff.content
        assert company.name == "TechCorp"  # type: ignore[attr-defined]
        assert type(company.headquarters).__name__ == "Address"  # type: ignore[attr-defined]
        assert company.headquarters.street == "123 Main St"  # type: ignore[attr-defined]
        assert company.headquarters.city == "Paris"  # type: ignore[attr-defined]
        assert company.headquarters.country == "France"  # type: ignore[attr-defined]

        pretty_print(company, title="Company with nested construct")
