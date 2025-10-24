import pytest

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.input_requirements import TypedNamedInputRequirement
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_content import TextContent
from tests.test_pipelines.tricky_questions import ThoughtfulAnswer


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestDryWorkingMemory:
    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_with_page_content(
        self,
    ):
        log.info("Testing dry run with PageContent")

        # Test the specific inputs requested by the user
        needed_inputs = [
            TypedNamedInputRequirement(
                variable_name="page",
                concept=ConceptFactory.make(
                    concept_code=NativeConceptCode.PAGE, domain="test_tricky_questions", description="Lorem Ipsum", structure_class_name="Page"
                ),
                structure_class=PageContent,
            ),
        ]

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)
        # Verify working memory contains exactly this
        assert len(dry_memory.root) == 1
        assert dry_memory.get_optional_stuff("page") is not None

        # Verify concept code is correct
        page_stuff = dry_memory.get_stuff("page")
        assert page_stuff.concept.code == NativeConceptCode.PAGE
        assert page_stuff.stuff_name == "page"

        # Verify structured content was created properly
        page_content = page_stuff.content
        assert isinstance(page_content, PageContent)

        # Verify PageContent has the expected structure
        assert hasattr(page_content, "text_and_images")
        assert hasattr(page_content, "page_view")

        # Verify text_and_images field exists and has mock data
        assert page_content.text_and_images is not None

        # Verify page_view field exists (it's Optional so could be None)
        assert hasattr(page_content, "page_view")

    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_with_structured_content(
        self,
    ):
        log.info("Testing dry run with structured content (ThoughtfulAnswer)")

        # Use ThoughtfulAnswer from tricky questions domain
        needed_inputs = [
            TypedNamedInputRequirement(
                variable_name="thoughtful_answer",
                concept=ConceptFactory.make(
                    concept_code="ThoughtfulAnswer",
                    domain="test_tricky_questions",
                    description="Thoughtful answer",
                    structure_class_name="ThoughtfulAnswer",
                ),
                structure_class=ThoughtfulAnswer,
            ),
            TypedNamedInputRequirement(
                variable_name="question",
                concept=ConceptFactory.make(concept_code="Question", domain="answer", description="Question", structure_class_name="Question"),
                structure_class=TextContent,
            ),
        ]

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)
        expected_number_of_elements_in_memory = 2

        assert len(dry_memory.root) == expected_number_of_elements_in_memory
        assert dry_memory.get_optional_stuff("thoughtful_answer") is not None
        assert dry_memory.get_optional_stuff("question") is not None

        # Verify concept codes are preserved
        thoughtful_answer_stuff = dry_memory.get_stuff("thoughtful_answer")
        assert thoughtful_answer_stuff.concept.code == "ThoughtfulAnswer"
        assert thoughtful_answer_stuff.concept.domain == "test_tricky_questions"

        question_stuff = dry_memory.get_stuff("question")
        assert question_stuff.concept.code == "Question"
        assert question_stuff.concept.domain == "answer"

        # Verify structured content was created properly
        thoughtful_answer_content = thoughtful_answer_stuff.content
        assert isinstance(thoughtful_answer_content, ThoughtfulAnswer)
        assert hasattr(thoughtful_answer_content, "the_trap")
        assert hasattr(thoughtful_answer_content, "the_counter")
        assert hasattr(thoughtful_answer_content, "the_lesson")
        assert hasattr(thoughtful_answer_content, "the_answer")

        # Verify all fields have mock values
        assert thoughtful_answer_content.the_trap is not None
        assert thoughtful_answer_content.the_counter is not None
        assert thoughtful_answer_content.the_lesson is not None
        assert thoughtful_answer_content.the_answer is not None

        log.info("Created mock working memory with structured content:")
        dry_memory.pretty_print_summary()

    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_with_text_content_fallback(
        self,
    ):
        log.info("Testing dry run with TextContent fallback")

        needed_inputs = [
            TypedNamedInputRequirement(
                variable_name="question_analysis",
                concept=ConceptFactory.make(
                    concept_code="QuestionAnalysis",
                    domain="test_tricky_questions",
                    description="Question analysis",
                    structure_class_name="QuestionAnalysis",
                ),
                structure_class=TextContent,
            ),
            TypedNamedInputRequirement(
                variable_name="conclusion",
                concept=ConceptFactory.make(
                    concept_code="ThoughtfulAnswerConclusion",
                    domain="test_tricky_questions",
                    description="Thoughtful answer conclusion",
                    structure_class_name="ThoughtfulAnswerConclusion",
                ),
                structure_class=TextContent,
            ),
        ]

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)

        assert len(dry_memory.root) == 2
        assert dry_memory.get_optional_stuff("question_analysis") is not None
        assert dry_memory.get_optional_stuff("conclusion") is not None

        # Verify both use TextContent
        question_analysis_stuff = dry_memory.get_stuff("question_analysis")
        assert isinstance(question_analysis_stuff.content, TextContent)
        assert question_analysis_stuff.concept.code == "QuestionAnalysis"

        conclusion_stuff = dry_memory.get_stuff("conclusion")
        assert isinstance(conclusion_stuff.content, TextContent)
        assert conclusion_stuff.concept.code == "ThoughtfulAnswerConclusion"
        assert conclusion_stuff.concept.domain == "test_tricky_questions"

        log.info("Created mock working memory with TextContent fallback:")
        dry_memory.pretty_print_summary()

    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_mixed_content_types(
        self,
    ):
        log.info("Testing dry run with mixed content types")

        needed_inputs = [
            TypedNamedInputRequirement(
                variable_name="thoughtful_answer",
                concept=ConceptFactory.make(
                    concept_code="ThoughtfulAnswer",
                    domain="test_tricky_questions",
                    description="Thoughtful answer",
                    structure_class_name="ThoughtfulAnswer",
                ),
                structure_class=ThoughtfulAnswer,
            ),
            TypedNamedInputRequirement(
                variable_name="raw_question",
                concept=ConceptFactory.make(concept_code="Question", domain="answer", description="Question", structure_class_name="Question"),
                structure_class=TextContent,
            ),
            TypedNamedInputRequirement(
                variable_name="analysis_result",
                concept=ConceptFactory.make(
                    concept_code="QuestionAnalysis",
                    domain="test_tricky_questions",
                    description="Question analysis",
                    structure_class_name="QuestionAnalysis",
                ),
                structure_class=TextContent,
            ),
        ]

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)

        assert len(dry_memory.root) == 3

        # Verify structured content
        thoughtful_answer_stuff = dry_memory.get_stuff("thoughtful_answer")
        assert isinstance(thoughtful_answer_stuff.content, ThoughtfulAnswer)
        assert thoughtful_answer_stuff.concept.code == "ThoughtfulAnswer"
        assert thoughtful_answer_stuff.concept.domain == "test_tricky_questions"

        # Verify text content
        raw_question_stuff = dry_memory.get_stuff("raw_question")
        assert isinstance(raw_question_stuff.content, TextContent)
        assert raw_question_stuff.concept.code == "Question"
        assert raw_question_stuff.concept.domain == "answer"

        analysis_result_stuff = dry_memory.get_stuff("analysis_result")
        assert isinstance(analysis_result_stuff.content, TextContent)
        assert analysis_result_stuff.concept.code == "QuestionAnalysis"
        assert analysis_result_stuff.concept.domain == "test_tricky_questions"

        log.info("Created mock working memory with mixed content types:")
        dry_memory.pretty_print_summary()

    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_empty_inputs(
        self,
    ):
        log.info("Testing dry run with empty inputs")

        needed_inputs: list[TypedNamedInputRequirement] = []

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)

        # Verify empty memory was created
        assert len(dry_memory.root) == 0
        assert dry_memory.root == {}

        log.info("Created empty mock working memory")

    @pytest.mark.usefixtures("request")
    async def test_make_for_dry_run_realistic_pipeline_scenario(self):
        log.info("Testing dry run with realistic tricky questions pipeline scenario")

        # Simulate the conclude_tricky_question_by_steps pipeline needs
        needed_inputs = [
            TypedNamedInputRequirement(
                variable_name="question",
                concept=ConceptFactory.make(concept_code="Question", domain="answer", description="Question", structure_class_name="Question"),
                structure_class=TextContent,
            ),
            TypedNamedInputRequirement(
                variable_name="question_analysis",
                concept=ConceptFactory.make(
                    concept_code="QuestionAnalysis",
                    domain="test_tricky_questions",
                    description="Question analysis",
                    structure_class_name="QuestionAnalysis",
                ),
                structure_class=TextContent,
            ),
            TypedNamedInputRequirement(
                variable_name="thoughtful_answer",
                concept=ConceptFactory.make(
                    concept_code="ThoughtfulAnswer",
                    domain="test_tricky_questions",
                    description="Thoughtful answer",
                    structure_class_name="ThoughtfulAnswer",
                ),
                structure_class=ThoughtfulAnswer,
            ),
        ]

        dry_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs)

        # Verify the complete pipeline inputs are mocked
        assert len(dry_memory.root) == 3

        # Test question input
        question_stuff = dry_memory.get_stuff("question")
        assert isinstance(question_stuff.content, TextContent)
        assert len(question_stuff.content.text) > 0  # Should have mock text

        # Test question analysis input
        question_analysis_stuff = dry_memory.get_stuff("question_analysis")
        assert isinstance(question_analysis_stuff.content, TextContent)
        assert len(question_analysis_stuff.content.text) > 0  # Should have mock text

        # Test thoughtful answer input (structured)
        thoughtful_answer_stuff = dry_memory.get_stuff("thoughtful_answer")
        assert isinstance(thoughtful_answer_stuff.content, ThoughtfulAnswer)

        # Verify the ThoughtfulAnswer has all required fields with mock data
        ta_content = thoughtful_answer_stuff.content
        assert isinstance(ta_content.the_trap, str)
        assert len(ta_content.the_trap) > 0
        assert isinstance(ta_content.the_counter, str)
        assert len(ta_content.the_counter) > 0
        assert isinstance(ta_content.the_lesson, str)
        assert len(ta_content.the_lesson) > 0
        assert isinstance(ta_content.the_answer, str)
        assert len(ta_content.the_answer) > 0

        log.info("Created realistic pipeline mock memory:")
        dry_memory.pretty_print_summary()

        # Log the detailed thoughtful answer content for verification
        log.info("Mock ThoughtfulAnswer details:")
        log.info(f"  - the_trap: {ta_content.the_trap}")
        log.info(f"  - the_counter: {ta_content.the_counter}")
        log.info(f"  - the_lesson: {ta_content.the_lesson}")
        log.info(f"  - the_answer: {ta_content.the_answer}")
