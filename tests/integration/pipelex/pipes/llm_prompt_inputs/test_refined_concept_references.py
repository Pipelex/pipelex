"""Integration tests for refined Image/Document concept references in LLM prompts.

These tests verify that concepts which refine Image or Document work correctly
as LLM inputs, both at factory time (reference creation) and runtime (extraction).
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_required_concept
from pipelex.kernel.prompt_references import DocumentReferenceKind, ImageReferenceKind
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.cases import DocumentTestCases, ImageTestCases


class TestRefinedConceptReferences:
    """Tests that concepts refining Image/Document work correctly as LLM inputs."""

    def test_refined_image_concept_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that a concept refining Image creates a DIRECT image reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test refined Image concept",
            inputs={"photo": "refined_concepts_test.Photo"},
            output="Text",
            prompt="Describe this photo: $photo",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_refined_image_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT
        assert ref.variable_path == "photo"

    def test_refined_document_concept_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that a concept refining Document creates a DIRECT document reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test refined Document concept",
            inputs={"report": "refined_concepts_test.Report"},
            output="Text",
            prompt="Summarize this report: $report",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_refined_document_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_document_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT
        assert ref.variable_path == "report"

    @pytest.mark.asyncio
    async def test_refined_image_concept_extracted_to_user_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that refined Image concept is extracted to user_images at runtime."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test refined Image extraction",
            inputs={"photo": "refined_concepts_test.Photo"},
            output="Text",
            prompt="Describe: $photo",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_refined_image_extraction",
            blueprint=pipe_llm_blueprint,
        )

        photo_concept = get_required_concept("refined_concepts_test.Photo")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=photo_concept,
                content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                name="photo",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text

    @pytest.mark.asyncio
    async def test_refined_document_concept_extracted_to_user_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that refined Document concept is extracted to user_documents at runtime."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test refined Document extraction",
            inputs={"report": "refined_concepts_test.Report"},
            output="Text",
            prompt="Summarize: $report",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_refined_document_extraction",
            blueprint=pipe_llm_blueprint,
        )

        report_concept = get_required_concept("refined_concepts_test.Report")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=report_concept,
                content=DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_1),
                name="report",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 1
        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text
