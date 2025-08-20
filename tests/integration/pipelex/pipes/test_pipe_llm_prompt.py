from typing import List, Tuple, Type

import pytest

from pipelex.core.concepts.concept_native import NativeConcept
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt, PipeLLMPromptOutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from tests.integration.pipelex.test_data import PipeTestCases
from tests.test_pipelines.pipe_llm_prompt import (
    ComplexListContent,
    DocumentTypeContent,
    MusicCategoryContent,
    PersonContent,
    SimpleStructuredContent,
    SimpleTextContent,
)


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMPrompt:
    async def test_simple_prompt(self, pipe_run_mode: PipeRunMode):
        """Test basic prompt with system and user text."""
        pipe_llm_prompt = PipeLLMPrompt(
            code="test_simple_prompt",
            domain="generic",
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            user_text=PipeTestCases.USER_PROMPT,
            output_concept_code=NativeConcept.TEXT.code,
        )

        pipe_output: PipeLLMPromptOutput = await get_pipe_router().run_pipe_job(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=pipe_llm_prompt,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            )
        )

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.llm_prompt is not None
        assert pipe_output.llm_prompt.user_text is not None
        assert pipe_output.llm_prompt.user_text.endswith(
            PipeLLMPrompt.get_output_structure_prompt(NativeConcept.TEXT.code, is_with_preliminary_text=False)
        )

    async def test_prompt_with_images(self, pipe_run_mode: PipeRunMode):
        """Test prompt with image inputs."""
        stuff_name = "image"
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=PipeTestCases.SIMPLE_STUFF_IMAGE)

        pipe_llm_prompt = PipeLLMPrompt(
            code="test_prompt_with_images",
            domain="generic",
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            user_text=PipeTestCases.MULTI_IMG_DESC_PROMPT,
            user_images=[stuff_name],  # Just use the stuff name, the content will be extracted as ImageContent
            output_concept_code=NativeConcept.TEXT.code,
        )

        pipe_output: PipeLLMPromptOutput = await get_pipe_router().run_pipe_job(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=pipe_llm_prompt,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
            )
        )

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

    async def test_prompt_with_output_structure(self, pipe_run_mode: PipeRunMode):
        """Test prompt with output structure for different content types."""
        test_cases: List[Tuple[Type[StructuredContent], str, str]] = [
            (SimpleTextContent, "Empty class inheritance", "test.SimpleTextContent"),
            (SimpleStructuredContent, "Primitive types", "test.SimpleStructuredContent"),
            (DocumentTypeContent, "Enum fields", "test.DocumentTypeContent"),
            (PersonContent, "Nested content", "test.PersonContent"),
            (ComplexListContent, "List content", "test.ComplexListContent"),
            (MusicCategoryContent, "Music genre", "test.MusicCategoryContent"),
        ]

        for content_class, description, concept_code in test_cases:
            pipe_llm_prompt = PipeLLMPrompt(
                code=f"test_output_structure_{content_class.__name__}",
                domain="generic",
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                user_text=f"Generate content for {description}",
                output_concept_code=concept_code,
            )

            pipe_output: PipeLLMPromptOutput = await get_pipe_router().run_pipe_job(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=pipe_llm_prompt,
                    pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                )
            )

            assert pipe_output is not None
            assert pipe_output.working_memory is not None
            assert pipe_output.main_stuff is not None

            # Verify output structure is appended
            output_structure = pipe_llm_prompt.get_output_structure_prompt(concept_code, is_with_preliminary_text=False)

            assert pipe_output.llm_prompt is not None
            assert pipe_output.llm_prompt.user_text is not None
            assert output_structure in pipe_output.llm_prompt.user_text

            # Verify docstrings and field descriptions are included
            if content_class.__doc__:
                assert content_class.__doc__ in output_structure

            # Verify field descriptions
            for _, field in content_class.model_fields.items():
                if field.description:
                    assert field.description in output_structure

    async def test_prompt_with_prompting_style(self, pipe_run_mode: PipeRunMode):
        """Test prompt with different prompting styles."""
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.PLAIN,
        )
        pipe_llm_prompt = PipeLLMPrompt(
            code="test_prompting_style",
            domain="generic",
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            user_text=PipeTestCases.USER_PROMPT,
            prompting_style=prompting_style,
            output_concept_code=NativeConcept.TEXT.code,
        )

        pipe_output: PipeLLMPromptOutput = await get_pipe_router().run_pipe_job(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=pipe_llm_prompt,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            )
        )

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

    async def test_prompt_validation_errors(self):
        """Test validation errors for invalid prompt configurations."""
        # Test missing user text
        with pytest.raises(Exception) as exc_info:
            PipeLLMPrompt(
                code="test_validation_error",
                domain="generic",
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                output_concept_code=NativeConcept.TEXT.code,
            )
        assert "must have exactly one of user_text" in str(exc_info.value)

        # Test multiple user text sources
        with pytest.raises(Exception) as exc_info:
            PipeLLMPrompt(
                code="test_validation_error",
                domain="generic",
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                user_text=PipeTestCases.USER_PROMPT,
                user_prompt_verbatim_name="some_template",
                output_concept_code=NativeConcept.TEXT.code,
            )
        assert "must have exactly one of user_text" in str(exc_info.value)

        # Test multiple system prompts
        with pytest.raises(Exception) as exc_info:
            PipeLLMPrompt(
                code="test_validation_error",
                domain="generic",
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                system_prompt_verbatim_name="some_template",
                user_text=PipeTestCases.USER_PROMPT,
                output_concept_code=NativeConcept.TEXT.code,
            )
        assert "got more than one of system_prompt" in str(exc_info.value)
