"""Integration tests for [Document N] token substitution in prompt text."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_native_concept
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.urls import URLs


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
            prompt="Analyze this document: $document",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_doc_token_sub",
            blueprint=pipe_llm_blueprint,
        )

        doc_url = URLs.pdf_example_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url=doc_url),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            templating_style=resolve_templating_style(authored=pipe_llm.templating_style),
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

        doc_url = URLs.pdf_example_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=DocumentContent(url=doc_url),
                name="document",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            templating_style=resolve_templating_style(authored=pipe_llm.templating_style),
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

        doc_urls = [URLs.pdf_example_1, URLs.pdf_example_2]
        doc_list = ListContent[DocumentContent](items=[DocumentContent(url=url) for url in doc_urls])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.DOCUMENT),
                content=doc_list,
                name="documents",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            templating_style=resolve_templating_style(authored=pipe_llm.templating_style),
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
                DocumentContent(url=URLs.pdf_example_1),
                DocumentContent(url=URLs.pdf_example_2),
            ]
        )
        docs_b = ListContent[DocumentContent](
            items=[
                DocumentContent(url=URLs.pdf_example_1),
                DocumentContent(url=URLs.pdf_example_2),
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
            templating_style=resolve_templating_style(authored=pipe_llm.templating_style),
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Document 1]" in llm_prompt.user_text
        assert "[Document 2]" in llm_prompt.user_text
        assert "[Document 3]" in llm_prompt.user_text
        assert "[Document 4]" in llm_prompt.user_text
