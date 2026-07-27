from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelSimple:
    async def test_parallel_text_analysis(
        self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeParallel running three text analysis pipes in parallel."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_parallel")])
        # Create PipeParallel instance - pipes are loaded from MTHDS files
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel text analysis pipeline",
            inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.COMPOSITE}",
            branches=[
                SubPipeBlueprint(pipe="analyze_sentiment", result="sentiment_result"),
                SubPipeBlueprint(pipe="count_words", result="word_count_result"),
                SubPipeBlueprint(pipe="extract_keywords", result="keywords_result"),
            ],
            add_each_output=True,
        )

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code="test_integration",
            pipe_code="parallel_text_analyzer",
            blueprint=pipe_parallel_blueprint,
        )

        # Create test data
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="The weather is beautiful today. I love sunny days and outdoor activities."),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Verify the PipeParallel instance was created correctly
        assert pipe_parallel.domain_code == "test_integration"
        assert pipe_parallel.code == "parallel_text_analyzer"
        assert len(pipe_parallel.parallel_sub_pipes) == 3
        assert pipe_parallel.add_each_output is True

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
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name="parallel_results",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Verify working memory structure - original input + 3 parallel results + combined output
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 5

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
        if pipe_run_mode.is_live:
            assert sentiment_result.content.text.lower() in {"positive", "negative", "neutral"}
        assert f"{sentiment_result.concept.domain_code}.{sentiment_result.concept.code}" == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"

        # Verify word count result
        word_count_result = final_working_memory.get_stuff("word_count_result")
        assert word_count_result is not None
        assert isinstance(word_count_result.content, TextContent)
        # Should be a number (as text)
        word_count_text = word_count_result.content.text.strip()
        if pipe_run_mode.is_live:
            assert word_count_text.isdigit() or word_count_text in {"12", "thirteen", "twelve"}  # Allow for some variation
        assert word_count_result.concept.code == "Text"
        assert word_count_result.concept.domain_code == "native"

        # Verify keywords extraction result
        keywords_result = final_working_memory.get_stuff("keywords_result")
        assert keywords_result is not None
        assert isinstance(keywords_result.content, TextContent)
        # Should contain comma-separated keywords
        keywords_text = keywords_result.content.text.strip()
        if pipe_run_mode.is_live:
            assert "," in keywords_text or len(keywords_text.split()) >= 2  # Should have multiple keywords
        assert keywords_result.concept.code == "Text"
        assert keywords_result.concept.domain_code == "native"

        # Verify that all results are different (pipes ran independently)
        assert sentiment_result.content.text != word_count_result.content.text
        assert sentiment_result.content.text != keywords_result.content.text
        assert word_count_result.content.text != keywords_result.content.text

        # The parallel always combines: the main stuff is the composite of the branch outputs
        final_result = pipe_output.main_stuff
        assert final_result.concept.code == "Composite"
        assert isinstance(final_result.content, CompositeContent)
        assert set(final_result.content.components.keys()) == {"sentiment_result", "word_count_result", "keywords_result"}

    async def test_parallel_short_text_analysis(
        self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
    ):
        """Test PipeParallel with shorter text to verify consistent behavior."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_parallel")])
        # Create PipeParallel instance
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel text analysis pipeline for short text",
            inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.COMPOSITE}",
            branches=[
                SubPipeBlueprint(pipe="analyze_sentiment", result="sentiment_result"),
                SubPipeBlueprint(pipe="count_words", result="word_count_result"),
                SubPipeBlueprint(pipe="extract_keywords", result="keywords_result"),
            ],
            add_each_output=True,
        )

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code="test_integration",
            pipe_code="parallel_text_analyzer",
            blueprint=pipe_parallel_blueprint,
        )
        # Create test data - shorter text
        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="Hello world"),
            name="input_text",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        # Actually run the PipeParallel pipe
        pipe_output = await pipe_parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name="parallel_results",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify the pipe executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None

        # Verify working memory structure - original input + 3 parallel results + combined output
        final_working_memory = pipe_output.working_memory
        assert len(final_working_memory.root) == 5

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
        if pipe_run_mode.is_live:
            assert word_count_text in {"2", "two"} or word_count_text.isdigit()

        # Sentiment should be one of the valid values
        if pipe_run_mode.is_live:
            assert sentiment_result.content.text.lower() in {"positive", "negative", "neutral"}
