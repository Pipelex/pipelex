"""Integration tests for the assemble_pipelex_bundle_spec pipe.

These tests verify that the assemble_pipelex_bundle_spec pipe correctly
assembles a PipelexBundleSpec from working memory containing concept specs,
pipe specs, and bundle header spec.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pytest

from pipelex import pretty_print
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.test_data import AssemblePipelexBundleSpecTestCases

if TYPE_CHECKING:
    from pipelex.builder.concept.concept_spec import ConceptSpec
    from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec


@pytest.mark.asyncio(loop_scope="class")
class TestAssemblePipelexBundleSpec:
    """Integration tests for the assemble_pipelex_bundle_spec pipe."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the builder library."""
        return [Path("pipelex/builder")]

    @pytest.fixture
    def working_memory_with_specs(self, load_test_library: Callable[[list[Path]], None], test_library_path: list[Path]) -> WorkingMemory:
        """Create working memory with concept specs, pipe specs, and bundle header spec."""
        load_test_library(test_library_path)

        working_memory = WorkingMemory()

        # Add concept_specs as a list
        concept_specs_content: ListContent[ConceptSpec] = ListContent(items=AssemblePipelexBundleSpecTestCases.CONCEPT_SPECS)
        concept_specs_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=concept_specs_content,
            name="concept_specs",
        )
        working_memory.add_new_stuff(name="concept_specs", stuff=concept_specs_stuff)

        # Add pipe_specs as a list
        pipe_specs_content: ListContent[PipeLLMSpec] = ListContent(items=AssemblePipelexBundleSpecTestCases.PIPE_SPECS)
        pipe_specs_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=pipe_specs_content,
            name="pipe_specs",
        )
        working_memory.add_new_stuff(name="pipe_specs", stuff=pipe_specs_stuff)

        # Add bundle_header_spec
        bundle_header_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=AssemblePipelexBundleSpecTestCases.BUNDLE_HEADER,
            name="bundle_header_spec",
        )
        working_memory.add_new_stuff(name="bundle_header_spec", stuff=bundle_header_stuff)

        return working_memory

    async def test_assemble_pipelex_bundle_spec_pipe_exists(
        self,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that the assemble_pipelex_bundle_spec pipe is registered in the builder domain."""
        load_test_library(test_library_path)

        pipe = get_pipe_library().get_required_pipe(pipe_code="assemble_pipelex_bundle_spec")
        assert pipe is not None
        assert pipe.code == "assemble_pipelex_bundle_spec"

    async def test_assemble_pipelex_bundle_spec_run(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
        working_memory_with_specs: WorkingMemory,
    ):
        """Test running the assemble_pipelex_bundle_spec pipe to assemble a PipelexBundleSpec."""
        load_test_library(test_library_path)

        # Get the pipe from the library
        pipe = get_pipe_library().get_required_pipe(pipe_code="assemble_pipelex_bundle_spec")
        assert pipe is not None

        # Create and run the pipe job
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory_with_specs,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        # Verify the output
        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None

        # Check that the output is a PipelexBundleSpec
        content = main_stuff.content
        assert isinstance(content, PipelexBundleSpec), f"Expected PipelexBundleSpec, got {type(content)}"

        # Verify the assembled bundle spec
        bundle_spec = content
        assert bundle_spec.domain == "test_domain"
        assert bundle_spec.description == "A test domain for assembly testing."
        assert bundle_spec.main_pipe == "generate_plan"

        # Verify concepts were assembled
        assert bundle_spec.concept is not None
        assert "UserBrief" in bundle_spec.concept
        assert "PlanDraft" in bundle_spec.concept

        # Verify pipes were assembled
        assert bundle_spec.pipe is not None
        assert "generate_plan" in bundle_spec.pipe

        pretty_print(bundle_spec, title="Assembled PipelexBundleSpec")
