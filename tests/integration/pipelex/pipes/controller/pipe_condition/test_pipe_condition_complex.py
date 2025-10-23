"""Complex integration test for PipeCondition controller with multiple inputs and nested conditions."""

from typing import Literal, cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import PipeRouterError
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_pipelines.pipe_controllers.pipe_condition.pipe_condition_complex import (
    DocumentRequest,
    UserProfile,
)


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.llm
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionComplex:
    async def test_technical_urgent_routing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test technical document with urgent priority routing."""
        # Create complex input data
        doc_request = DocumentRequest(document_type="technical", priority="urgent", language="english", complexity="high")
        user_profile = UserProfile(user_level="expert", department="technical")

        # Create stuffs for working memory
        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        pretty_print(pipe_output, title="Technical Urgent Processing")

        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        final_result = pipe_output.main_stuff
        assert isinstance(final_result.content, TextContent)
        if pipe_run_mode != PipeRunMode.DRY:
            assert "URGENT_TECHNICAL_PROCESSED" in final_result.content.text

    async def test_business_finance_routing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test business document for finance department routing."""
        doc_request = DocumentRequest(document_type="business", priority="normal", language="english", complexity="medium")
        user_profile = UserProfile(user_level="intermediate", department="finance")

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        pretty_print(pipe_output, title="Business Finance Processing")

        assert pipe_output is not None
        if pipe_run_mode != PipeRunMode.DRY:
            final_result = pipe_output.main_stuff
            assert isinstance(final_result.content, TextContent)
            assert "FINANCE_BUSINESS_PROCESSED" in final_result.content.text

    async def test_legal_complex_routing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test complex legal document routing."""
        doc_request = DocumentRequest(document_type="legal", priority="normal", language="spanish", complexity="high")
        user_profile = UserProfile(user_level="expert", department="legal")

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        pretty_print(pipe_output, title="Legal Complex Processing")

        assert pipe_output is not None
        if pipe_run_mode != PipeRunMode.DRY:
            final_result = pipe_output.main_stuff
            assert isinstance(final_result.content, TextContent)
            assert "COMPLEX_LEGAL_PROCESSED" in final_result.content.text

    async def test_technical_expert_high_complexity_routing(self, request: FixtureRequest, pipe_run_mode: PipeRunMode):
        """Test technical document with expert user and high complexity."""
        doc_request = DocumentRequest(
            document_type="technical",
            priority="normal",  # Not urgent, so should check user level + complexity
            language="english",
            complexity="high",
        )
        user_profile = UserProfile(
            user_level="expert",  # Expert + high complexity should route to expert_tech
            department="technical",
        )

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        pretty_print(pipe_output, title="Technical Expert High Complexity Processing")

        assert pipe_output is not None
        if pipe_run_mode != PipeRunMode.DRY:
            final_result = pipe_output.main_stuff
            assert isinstance(final_result.content, TextContent)
            assert "EXPERT_TECHNICAL_PROCESSED" in final_result.content.text

    # DRY RUN TESTS
    async def test_complex_pipeline_dry_run_success(self, request: FixtureRequest):
        """Test complex pipeline dry run with valid inputs - should succeed."""
        doc_request = DocumentRequest(document_type="business", priority="urgent", language="english", complexity="low")
        user_profile = UserProfile(user_level="beginner", department="marketing")

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        pretty_print(pipe_output, title="Complex Pipeline Dry Run")

        assert pipe_output is not None
        assert pipe_output.working_memory is not None

    async def test_complex_pipeline_dry_run_missing_inputs(self, request: FixtureRequest):
        """Test complex pipeline dry run with missing inputs - should fail with PipeRouterError."""
        doc_request = DocumentRequest(document_type="technical", priority="urgent", language="english", complexity="high")

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(doc_stuff)

        with pytest.raises(PipeRouterError) as exc_info:
            await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=get_required_pipe(pipe_code="complex_document_processor"),
                    pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
                    working_memory=working_memory,
                    job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                ),
            )

        error = exc_info.value
        assert error.pipe_code == "complex_document_processor"
        assert error.missing_inputs is not None
        assert "user_profile" in error.missing_inputs
        assert "missing required inputs" in str(error)

    @pytest.mark.parametrize(
        ("doc_type", "priority", "user_level", "department", "complexity", "language", "expected_output_contains"),
        [
            ("technical", "urgent", "beginner", "technical", "low", "english", "URGENT_TECHNICAL_PROCESSED"),
            ("technical", "normal", "expert", "technical", "high", "english", "EXPERT_TECHNICAL_PROCESSED"),
            ("technical", "normal", "beginner", "technical", "low", "english", "STANDARD_TECHNICAL_PROCESSED"),
            ("business", "urgent", "intermediate", "finance", "medium", "english", "URGENT_BUSINESS_PROCESSED"),
            ("business", "normal", "intermediate", "finance", "medium", "english", "FINANCE_BUSINESS_PROCESSED"),
            ("business", "normal", "beginner", "marketing", "low", "spanish", "MARKETING_BUSINESS_PROCESSED"),
            ("business", "normal", "expert", "operations", "high", "english", "GENERAL_BUSINESS_PROCESSED"),
            ("legal", "normal", "expert", "legal", "high", "english", "COMPLEX_LEGAL_PROCESSED"),
            ("legal", "normal", "intermediate", "legal", "medium", "french", "INTERNATIONAL_LEGAL_PROCESSED"),
            ("legal", "low", "beginner", "legal", "low", "english", "STANDARD_LEGAL_PROCESSED"),
        ],
    )
    async def test_complex_routing_scenarios_dry_run(
        self,
        doc_type: Literal["technical", "business", "legal"],
        priority: Literal["urgent", "normal", "low"],
        user_level: Literal["beginner", "intermediate", "expert"],
        department: Literal["finance", "marketing", "legal", "technical", "operations"],
        complexity: Literal["low", "medium", "high"],
        language: Literal["english", "spanish", "french", "german", "chinese"],
        expected_output_contains: str,
        request: FixtureRequest,
        pipe_run_mode: PipeRunMode,
    ):
        doc_request = DocumentRequest(
            document_type=doc_type,
            priority=priority,
            language=language,
            complexity=complexity,
        )
        user_profile = UserProfile(
            user_level=user_level,
            department=department,
        )

        doc_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentRequest",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.DocumentRequest",
                structure_class_name="DocumentRequest",
            ),
            content=doc_request,
            name="doc_request",
        )
        user_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="UserProfile",
                domain="test_pipe_condition_complex",
                description="test_pipe_condition_complex.UserProfile",
                structure_class_name="UserProfile",
            ),
            content=user_profile,
            name="user_profile",
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([doc_stuff, user_stuff])

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="complex_document_processor"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=cast("str", request.node.originalname)),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        if pipe_run_mode == PipeRunMode.LIVE:
            assert expected_output_contains in pipe_output.main_stuff_as_str
