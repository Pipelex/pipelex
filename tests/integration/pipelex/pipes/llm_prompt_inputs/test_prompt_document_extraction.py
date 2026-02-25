"""Integration tests for document extraction into user_documents list."""

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
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.urls import URLs


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
                content=DocumentContent(url=URLs.pdf_example_1),
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
                DocumentContent(url=URLs.pdf_example_1),
                DocumentContent(url=URLs.pdf_example_2),
                DocumentContent(url=URLs.pdf_example_3),
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
                    content=DocumentContent(url=URLs.pdf_example_1),
                    name="doc",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=ImageContent(url=URLs.png_example_1),
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
                content=DocumentContent(url=URLs.pdf_example_1),
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
