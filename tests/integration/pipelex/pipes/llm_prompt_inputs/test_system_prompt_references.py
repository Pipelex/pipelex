"""Integration tests for image/document references in system prompts."""

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
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_operators.llm.document_reference import DocumentReferenceKind
from pipelex.pipe_operators.llm.image_reference import ImageReferenceKind
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.cases import DocumentTestCases, ImageTestCases


class TestSystemPromptReferences:
    """Tests for image/document references in system prompts."""

    def test_direct_image_in_system_prompt_creates_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image input in system_prompt creates a system_image_references entry."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt image reference",
            inputs={"image": "Image"},
            output="Text",
            system_prompt="Context image: $image",
            prompt="Describe what you see",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_image_ref",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.system_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.system_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.system_image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT
        assert ref.variable_path == "image"
        # User prompt should have no image references
        assert pipe_llm.llm_prompt_spec.user_image_references is None

    def test_direct_list_images_in_system_prompt_creates_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] input in system_prompt creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt image list reference",
            inputs={"images": "Image[]"},
            output="Text",
            system_prompt="Reference images: $images",
            prompt="Analyze the images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_image_list_ref",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.system_image_references is not None
        assert len(pipe_llm.llm_prompt_spec.system_image_references) == 1
        ref = pipe_llm.llm_prompt_spec.system_image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT_LIST
        assert ref.variable_path == "images"

    def test_direct_document_in_system_prompt_creates_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document input in system_prompt creates a system_document_references entry."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt document reference",
            inputs={"document": "Document"},
            output="Text",
            system_prompt="Reference document: $document",
            prompt="Summarize the document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_doc_ref",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.system_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.system_document_references) == 1
        ref = pipe_llm.llm_prompt_spec.system_document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT
        assert ref.variable_path == "document"
        # User prompt should have no document references
        assert pipe_llm.llm_prompt_spec.user_document_references is None

    def test_direct_list_documents_in_system_prompt_creates_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Document[] input in system_prompt creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt document list reference",
            inputs={"documents": "Document[]"},
            output="Text",
            system_prompt="Reference documents: $documents",
            prompt="Compare the documents",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_doc_list_ref",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.system_document_references is not None
        assert len(pipe_llm.llm_prompt_spec.system_document_references) == 1
        ref = pipe_llm.llm_prompt_spec.system_document_references[0]
        assert ref.kind == DocumentReferenceKind.DIRECT_LIST
        assert ref.variable_path == "documents"

    @pytest.mark.asyncio
    async def test_system_prompt_image_extracted_to_user_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that image in system_prompt is extracted to user_images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt image extraction",
            inputs={"image": "Image"},
            output="Text",
            system_prompt="Context: $image",
            prompt="Describe what you see",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_image_extraction",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Image should be extracted
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1
        # System text should have the image token
        assert llm_prompt.system_text is not None
        assert "[Image 1]" in llm_prompt.system_text

    @pytest.mark.asyncio
    async def test_system_prompt_document_extracted_to_user_documents(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that document in system_prompt is extracted to user_documents."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt document extraction",
            inputs={"document": "Document"},
            output="Text",
            system_prompt="Context: $document",
            prompt="Summarize",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_doc_extraction",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_1),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Document should be extracted
        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 1
        # System text should have the document token
        assert llm_prompt.system_text is not None
        assert "[Document 1]" in llm_prompt.system_text

    @pytest.mark.asyncio
    async def test_images_in_both_prompts_have_global_numbering(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that images in system_prompt and user prompt have global sequential numbering.

        System prompt images get lower numbers (extracted first).
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test global image numbering",
            inputs={"system_image": "Image", "user_image": "Image"},
            output="Text",
            system_prompt="System context: $system_image",
            prompt="User query with: $user_image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_global_numbering",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                    name="system_image",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
                    name="user_image",
                ),
            ],
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Both images should be extracted
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 2

        # System prompt image gets [Image 1] (extracted first)
        assert llm_prompt.system_text is not None
        assert "[Image 1]" in llm_prompt.system_text

        # User prompt image gets [Image 2] (extracted second)
        assert llm_prompt.user_text is not None
        assert "[Image 2]" in llm_prompt.user_text

    @pytest.mark.asyncio
    async def test_documents_in_both_prompts_have_global_numbering(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that documents in system_prompt and user prompt have global sequential numbering."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test global document numbering",
            inputs={"system_doc": "Document", "user_doc": "Document"},
            output="Text",
            system_prompt="System context: $system_doc",
            prompt="User query with: $user_doc",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_global_doc_numbering",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.DOCUMENT),
                    content=DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_1),
                    name="system_doc",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.DOCUMENT),
                    content=DocumentContent(url=DocumentTestCases.PDF_FILE_PATH_2),
                    name="user_doc",
                ),
            ],
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Both documents should be extracted
        assert llm_prompt.user_documents is not None
        assert len(llm_prompt.user_documents) == 2

        # System prompt document gets [Document 1] (extracted first)
        assert llm_prompt.system_text is not None
        assert "[Document 1]" in llm_prompt.system_text

        # User prompt document gets [Document 2] (extracted second)
        assert llm_prompt.user_text is not None
        assert "[Document 2]" in llm_prompt.user_text

    @pytest.mark.asyncio
    async def test_image_list_in_system_prompt_extracts_all(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] in system_prompt extracts all images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test system prompt image list extraction",
            inputs={"images": "Image[]"},
            output="Text",
            system_prompt="Reference images: $images",
            prompt="Analyze",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_system_image_list_extraction",
            blueprint=pipe_llm_blueprint,
        )

        image_list = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ]
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="images",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # All images should be extracted
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 2

        # System text should have both image tokens
        assert llm_prompt.system_text is not None
        assert "[Image 1]" in llm_prompt.system_text
        assert "[Image 2]" in llm_prompt.system_text
