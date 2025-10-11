from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_factory import PipeParallelFactory
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelSimple:
    async def test_parallel_text_analysis(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeParallel running three text analysis pipes in parallel."""
        # Create PipeParallel instance - pipes are loaded from PLX files
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel text analysis pipeline",
            inputs={"input_text": InputRequirementBlueprint(concept=f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}")},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}",
            parallels=[
                SubPipeBlueprint(pipe="analyze_sentiment", result="sentiment_result"),
                SubPipeBlueprint(pipe="count_words", result="word_count_result"),
                SubPipeBlueprint(pipe="extract_keywords", result="keywords_result"),
            ],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_integration",
            pipe_code="parallel_text_analyzer",
            blueprint=pipe_parallel_blueprint,
        )

        # Create test data
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            content=TextContent(text="The weather is beautiful today. I love sunny days and outdoor activities."),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the PipeParallel instance was created correctly
        assert pipe_parallel.domain == "test_integration"
        assert pipe_parallel.code == "parallel_text_analyzer"
        assert len(pipe_parallel.parallel_sub_pipes) == 3
        assert pipe_parallel.add_each_output is True
        assert pipe_parallel.combined_output is None

        # Verify sub-pipes configuration
        assert pipe_parallel.parallel_sub_pipes[0].pipe_code == "analyze_sentiment"
        assert pipe_parallel.parallel_sub_pipes[0].output_name == "sentiment_result"
        assert pipe_parallel.parallel_sub_pipes[1].pipe_code == "count_words"
        assert pipe_parallel.parallel_sub_pipes[1].output_name == "word_count_result"
        assert pipe_parallel.parallel_sub_pipes[2].pipe_code == "extract_keywords"
        assert pipe_parallel.parallel_sub_pipes[2].output_name == "keywords_result"

        # Verify the working memory has the correct structure
        input_text = working_memory.get_stuff("input_text")
        assert input_text is not None
        assert isinstance(input_text.content, TextContent)
        assert input_text.content.text == "The weather is beautiful today. I love sunny days and outdoor activities."

        # Actually run the PipeParallel pipe
        pipe_output = await pipe_parallel.run_pipe(
            job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            working_memory=working_memory,
            output_name="parallel_results",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify working memory structure - should have original input + 3 parallel results
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 4  # original input + 3 parallel outputs

        # Original input should still be there
        original_input = final_working_memory.get_stuff("input_text")
        assert original_input is not None
        assert isinstance(original_input.content, TextContent)
        assert original_input.content.text == "The weather is beautiful today. I love sunny days and outdoor activities."

        # Verify sentiment analysis result
        sentiment_result = final_working_memory.get_stuff("sentiment_result")
        assert sentiment_result is not None
        assert isinstance(sentiment_result.content, TextContent)
        # Should return one of: positive, negative, neutral
        if pipe_run_mode != PipeRunMode.DRY:
            assert sentiment_result.content.text.lower() in ["positive", "negative", "neutral"]
        assert f"{sentiment_result.concept.domain}.{sentiment_result.concept.code}" == f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}"

        # Verify word count result
        word_count_result = final_working_memory.get_stuff("word_count_result")
        assert word_count_result is not None
        assert isinstance(word_count_result.content, TextContent)
        # Should be a number (as text)
        word_count_text = word_count_result.content.text.strip()
        if pipe_run_mode != PipeRunMode.DRY:
            assert word_count_text.isdigit() or word_count_text in ["12", "thirteen", "twelve"]  # Allow for some variation
        assert word_count_result.concept.code == "Text"
        assert word_count_result.concept.domain == "native"

        # Verify keywords extraction result
        keywords_result = final_working_memory.get_stuff("keywords_result")
        assert keywords_result is not None
        assert isinstance(keywords_result.content, TextContent)
        # Should contain comma-separated keywords
        keywords_text = keywords_result.content.text.strip()
        if pipe_run_mode != PipeRunMode.DRY:
            assert "," in keywords_text or len(keywords_text.split()) >= 2  # Should have multiple keywords
        assert keywords_result.concept.code == "Text"
        assert keywords_result.concept.domain == "native"

        # Verify that all results are different (pipes ran independently)
        assert sentiment_result.content.text != word_count_result.content.text
        assert sentiment_result.content.text != keywords_result.content.text
        assert word_count_result.content.text != keywords_result.content.text

        # Verify the main stuff points to the input (since no combined_output is set)
        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        assert final_result.content.text == "The weather is beautiful today. I love sunny days and outdoor activities."

    async def test_parallel_short_text_analysis(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test PipeParallel with shorter text to verify consistent behavior."""
        # Create PipeParallel instance
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel text analysis pipeline for short text",
            inputs={"input_text": InputRequirementBlueprint(concept=f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}")},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptEnum.TEXT}",
            parallels=[
                SubPipeBlueprint(pipe="analyze_sentiment", result="sentiment_result"),
                SubPipeBlueprint(pipe="count_words", result="word_count_result"),
                SubPipeBlueprint(pipe="extract_keywords", result="keywords_result"),
            ],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_integration",
            pipe_code="parallel_text_analyzer",
            blueprint=pipe_parallel_blueprint,
        )
        # Create test data - shorter text
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            content=TextContent(text="Hello world"),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Actually run the PipeParallel pipe
        pipe_output = await pipe_parallel.run_pipe(
            job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            working_memory=working_memory,
            output_name="parallel_results",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None

        # Verify working memory structure
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 4  # original input + 3 parallel outputs

        # Original input should still be there
        original_input = final_working_memory.get_stuff("input_text")
        assert original_input is not None
        assert isinstance(original_input.content, TextContent)
        assert original_input.content.text == "Hello world"

        # Verify all three parallel results exist
        sentiment_result = final_working_memory.get_stuff("sentiment_result")
        word_count_result = final_working_memory.get_stuff("word_count_result")
        keywords_result = final_working_memory.get_stuff("keywords_result")

        assert sentiment_result is not None
        assert word_count_result is not None
        assert keywords_result is not None

        # All should be Text content
        assert isinstance(sentiment_result.content, TextContent)
        assert isinstance(word_count_result.content, TextContent)
        assert isinstance(keywords_result.content, TextContent)

        # For "Hello world" - word count should be around 2
        word_count_text = word_count_result.content.text.strip()
        if pipe_run_mode != PipeRunMode.DRY:
            assert word_count_text in ["2", "two"] or word_count_text.isdigit()

        # Sentiment should be one of the valid values
        if pipe_run_mode != PipeRunMode.DRY:
            assert sentiment_result.content.text.lower() in ["positive", "negative", "neutral"]
