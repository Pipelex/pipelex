"""Integration tests for DocumentReference creation at factory level."""

from pathlib import Path
from typing import Callable

from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.document_reference import DocumentReferenceKind
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestDocumentReferencesFactoryLevel:
    """Tests for DocumentReference creation at factory time (PipeFactory.make_from_blueprint)."""

    def test_direct_document_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document input creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT document reference",
            inputs={"document": "Document"},
            output="Text",
            prompt="Analyze: $document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_doc_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_document_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT
        assert ref.variable_path == "document"

    def test_document_list_creates_direct_list_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document[] input creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT_LIST document reference",
            inputs={"documents": "Document[]"},
            output="Text",
            prompt="Analyze: $documents",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_list_doc_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_document_references) == 1
        ref = pipe_llm.llm_prompt_spec.user_document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT_LIST
        assert ref.variable_path == "documents"

    def test_image_and_document_both_create_references(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that both Image and Document inputs create their respective references."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test mixed references",
            inputs={"doc": "Document", "image": "Image"},
            output="Text",
            prompt="Document:\n@doc\nImage:\n@image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_mixed_references",
            blueprint=pipe_llm_blueprint,
        )

        # Should have document reference
        assert pipe_llm.llm_prompt_spec.user_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_document_references) == 1
        assert pipe_llm.llm_prompt_spec.user_document_references[0].variable_path == "doc"

        # Should have image reference
        assert pipe_llm.llm_prompt_spec.user_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.user_image_references) == 1
        assert pipe_llm.llm_prompt_spec.user_image_references[0].variable_path == "image"

    def test_text_input_creates_no_document_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Text input does NOT create document reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no document reference for text",
            inputs={"text": "Text"},
            output="Text",
            prompt="Process: $text",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_doc_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.user_document_references is None
