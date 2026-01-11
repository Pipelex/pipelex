"""Integration tests for document inputs in LLM prompts.

This module tests the complete flow of document handling in PipeLLM:
1. Factory-level: DocumentReference creation from blueprints
2. Runtime: Prompt building with token substitution
3. Document extraction into user_documents
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_native_concept
from pipelex.pipe_operators.llm.document_reference import DocumentReferenceKind
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

# =============================================================================
# Factory-Level Tests: DocumentReference Creation
# =============================================================================


class TestDocumentReferencesFactoryLevel:
    """Tests for DocumentReference creation at factory time (PipeFactory.make_from_blueprint)."""

    def test_direct_document_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document input creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT document reference",
            inputs={"document": "Document"},
            output="Text",
            prompt="Analyze: @document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_doc_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.document_references is not None
        assert len(pipe_llm.llm_prompt_spec.document_references) == 1
        ref = pipe_llm.llm_prompt_spec.document_references[0]
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

        assert pipe_llm.llm_prompt_spec.document_references is not None
        assert len(pipe_llm.llm_prompt_spec.document_references) == 1
        ref = pipe_llm.llm_prompt_spec.document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT_LIST
        assert ref.variable_path == "documents"

    def test_image_and_document_both_create_references(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that both Image and Document inputs create their respective references."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test mixed references",
            inputs={"doc": "Document", "image": "Image"},
            output="Text",
            prompt="Document: @doc\nImage: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_mixed_references",
            blueprint=pipe_llm_blueprint,
        )

        # Should have document reference
        assert pipe_llm.llm_prompt_spec.document_references is not None
        assert len(pipe_llm.llm_prompt_spec.document_references) == 1
        assert pipe_llm.llm_prompt_spec.document_references[0].variable_path == "doc"

        # Should have image reference
        assert pipe_llm.llm_prompt_spec.image_references is not None
        assert len(pipe_llm.llm_prompt_spec.image_references) == 1
        assert pipe_llm.llm_prompt_spec.image_references[0].variable_path == "image"

    def test_text_input_creates_no_document_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Text input does NOT create document reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no document reference for text",
            inputs={"text": "Text"},
            output="Text",
            prompt="Process: @text",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_doc_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.document_references is None


# =============================================================================
# Prompt Token Substitution Tests
# =============================================================================


@pytest.mark.asyncio(loop_scope="class")
class TestPromptDocumentTokenSubstitution:
    """Tests for [Document N] token substitution in prompt text."""

    async def test_direct_document_replaced_with_token(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct Document input is replaced with [Document 1] token."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test document token substitution",
            inputs={"document": "Document"},
            output="Text",
            prompt="Analyze this document: @document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_doc_token_sub",
            blueprint=pipe_llm_blueprint,
        )

        doc_url = "https://example.com/report.pdf"
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url=doc_url),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text

    async def test_direct_document_url_not_in_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that document URL does not appear in prompt text."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test URL not in text",
            inputs={"document": "Document"},
            output="Text",
            prompt="@document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_doc_no_url",
            blueprint=pipe_llm_blueprint,
        )

        doc_url = "https://example.com/secret_report.pdf"
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url=doc_url),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert doc_url not in llm_prompt.user_text
        assert "secret_report" not in llm_prompt.user_text

    async def test_direct_list_items_replaced_with_tokens(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document[] items are replaced with [Document N] tokens."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test document list tokens",
            inputs={"documents": "Document[]"},
            output="Text",
            prompt="Analyze: $documents",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_doc_list_tokens",
            blueprint=pipe_llm_blueprint,
        )

        doc_urls = ["https://example.com/report1.pdf", "https://example.com/report2.pdf"]
        doc_list = ListContent[DocumentContent](items=[DocumentContent(url=url) for url in doc_urls])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=doc_list,
                name="documents",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text
        assert "[Document 2]" in llm_prompt.user_text

    async def test_multiple_document_lists_numbered_globally(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that multiple Document[] inputs are numbered globally."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test multiple document lists",
            inputs={"docs_a": "Document[]", "docs_b": "Document[]"},
            output="Text",
            prompt="First: $docs_a\nSecond: $docs_b",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_multiple_doc_lists",
            blueprint=pipe_llm_blueprint,
        )

        docs_a = ListContent[DocumentContent](
            items=[
                DocumentContent(url="https://example.com/a1.pdf"),
                DocumentContent(url="https://example.com/a2.pdf"),
            ]
        )
        docs_b = ListContent[DocumentContent](
            items=[
                DocumentContent(url="https://example.com/b1.pdf"),
                DocumentContent(url="https://example.com/b2.pdf"),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.DOCUMENT),
                    content=docs_a,
                    name="docs_a",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.DOCUMENT),
                    content=docs_b,
                    name="docs_b",
                ),
            ],
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text
        assert "[Document 2]" in llm_prompt.user_text
        assert "[Document 3]" in llm_prompt.user_text
        assert "[Document 4]" in llm_prompt.user_text


# =============================================================================
# Prompt Document Extraction Tests
# =============================================================================


@pytest.mark.asyncio(loop_scope="class")
class TestPromptDocumentExtraction:
    """Tests for document extraction into user_documents list."""

    async def test_direct_document_in_user_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct Document is added to user_documents."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test user_documents",
            inputs={"document": "Document"},
            output="Text",
            prompt="@document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_user_documents",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url="https://example.com/doc.pdf"),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 1

    async def test_direct_list_all_in_user_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that all documents from Document[] are in user_documents."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test list user_documents",
            inputs={"documents": "Document[]"},
            output="Text",
            prompt="$documents",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_list_user_documents",
            blueprint=pipe_llm_blueprint,
        )

        doc_list = ListContent[DocumentContent](
            items=[
                DocumentContent(url="https://example.com/doc1.pdf"),
                DocumentContent(url="https://example.com/doc2.pdf"),
                DocumentContent(url="https://example.com/doc3.pdf"),
            ]
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=doc_list,
                name="documents",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 3

    async def test_images_and_documents_both_extracted(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that both images and documents are extracted separately."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test images and documents",
            inputs={"doc": "Document", "image": "Image"},
            output="Text",
            prompt="Document: @doc\nImage: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_images_and_documents",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.DOCUMENT),
                    content=DocumentContent(url="https://example.com/doc.pdf"),
                    name="doc",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=ImageContent(url="https://example.com/image.png"),
                    name="image",
                ),
            ],
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Should have both documents and images
        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 1
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # Tokens should be separate
        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text
        assert "[Image 1]" in llm_prompt.user_text

    async def test_document_not_in_images_list(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that documents are NOT added to user_images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test document not in images",
            inputs={"document": "Document"},
            output="Text",
            prompt="@document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_doc_not_in_images",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url="https://example.com/doc.pdf"),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Documents should be in user_documents
        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 1

        # Documents should NOT be in user_images
        assert llm_prompt.user_images is None or len(llm_prompt.user_images) == 0
