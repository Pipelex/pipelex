"""Integration tests for [Image N] token substitution in prompt text."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_native_concept
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestPromptTextTokenSubstitution:
    """Tests for [Image N] token substitution in prompt text."""

    async def test_direct_image_replaced_with_token(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct Image input is replaced with [Image 1] token."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test token substitution",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this image: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_token_sub",
            blueprint=pipe_llm_blueprint,
        )

        image_url = ImageTestCases.IMAGE_FILE_PATH_PNG_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=image_url),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text

    async def test_direct_image_url_not_in_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that image URL does not appear in prompt text."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test URL not in text",
            inputs={"image": "Image"},
            output="Text",
            prompt="@image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_url",
            blueprint=pipe_llm_blueprint,
        )

        image_url = ImageTestCases.IMAGE_FILE_PATH_PNG_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=image_url),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert image_url not in llm_prompt.user_text
        assert "ai_lympics" not in llm_prompt.user_text

    async def test_direct_list_items_replaced_with_tokens(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] items are replaced with [Image N] tokens."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test list tokens",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="Analyze: $images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_list_tokens",
            blueprint=pipe_llm_blueprint,
        )

        image_urls = [ImageTestCases.IMAGE_FILE_PATH_PNG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_1]
        image_list = ListContent[ImageContent](items=[ImageContent(url=url) for url in image_urls])
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

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text

    async def test_multiple_lists_numbered_globally(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that multiple Image[] inputs are numbered globally."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test multiple lists",
            inputs={"collection_a": "Image[]", "collection_b": "Image[]"},
            output="Text",
            prompt="First: $collection_a\nSecond: $collection_b",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_multiple_lists",
            blueprint=pipe_llm_blueprint,
        )

        collection_a = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ]
        )
        collection_b = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_2),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_3),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=collection_a,
                    name="collection_a",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=collection_b,
                    name="collection_b",
                ),
            ],
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text
        assert "[Image 3]" in llm_prompt.user_text
        assert "[Image 4]" in llm_prompt.user_text

    async def test_no_filenames_in_prompt_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that no image filenames appear in prompt text."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no filenames",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="$images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_filenames",
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

        assert llm_prompt.user_text is not None
        assert "ai_lympics" not in llm_prompt.user_text
        assert "animal_lympics" not in llm_prompt.user_text
        assert ".png" not in llm_prompt.user_text
        assert ".jpg" not in llm_prompt.user_text
