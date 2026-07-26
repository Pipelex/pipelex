"""Integration tests for PipeCompose content type conversions.

These tests verify that PipeCompose correctly handles different content type conversions:
- TextContent to str field (extract .text)
- TextContent to TextContent field (keep object)
- TextContent subclass to subclass field (keep object)
- ListContent to list[X] field (extract items)
- ListContent to ListContent field (keep object)
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_native_concept, get_pipe_router
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.models_for_pipe_compose import (
    MarkdownText,
    TeamMember,
)
from tests.integration.pipelex.pipes.operator.pipe_compose_structured.test_data import ContentConversionTestData


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeContentConversions:
    """Integration tests for content type conversions in PipeCompose."""

    @pytest.fixture
    def test_library_path(self) -> list[Path]:
        """Path to the test library for these tests."""
        return [Path("tests/integration/pipelex/pipes/operator/pipe_compose_structured")]

    async def test_compose_text_content_to_str_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that TextContent is converted to str when target field expects str."""
        load_test_library(test_library_path)

        # Create working memory with TextContent
        title_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="My Report Title"),
            name="title_text",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="title_text", stuff=title_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose report with str field from TextContent",
                "inputs": {"title_text": "Text"},
                "construct": ContentConversionTestData.TEXT_TO_STR_CONSTRUCT,
                "output": "compose_structured_test.ReportWithStrField",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_text_to_str",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "ReportWithStrField"

        report = main_stuff.content
        # The title field is str, so TextContent.text should be extracted
        assert report.title == "My Report Title"  # type: ignore[attr-defined]
        assert isinstance(report.title, str)  # type: ignore[attr-defined]
        assert report.author == "Test Author"  # type: ignore[attr-defined]

        pretty_print(report, title="ReportWithStrField - TextContent to str")

    async def test_compose_text_content_to_text_content_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that TextContent is kept as-is when target field expects TextContent."""
        load_test_library(test_library_path)

        # Create working memory with TextContent
        title_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="My Report Title"),
            name="title_text",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="title_text", stuff=title_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose report with TextContent field from TextContent",
                "inputs": {"title_text": "Text"},
                "construct": ContentConversionTestData.TEXT_TO_TEXT_CONTENT_CONSTRUCT,
                "output": "compose_structured_test.ReportWithTextContent",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_text_to_text_content",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "ReportWithTextContent"

        report = main_stuff.content
        # The title_content field is TextContent, so the object should be kept
        assert isinstance(report.title_content, TextContent)  # type: ignore[attr-defined]
        assert report.title_content.text == "My Report Title"  # type: ignore[attr-defined]
        assert report.description == "A description"  # type: ignore[attr-defined]

        pretty_print(report, title="ReportWithTextContent - TextContent to TextContent")

    async def test_compose_text_content_subclass_to_subclass_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that TextContent subclass is kept as-is when target field expects subclass."""
        load_test_library(test_library_path)

        # Create working memory with MarkdownText (TextContent subclass)
        markdown_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=MarkdownText(text="# Markdown Title\n\nSome content here."),
            name="markdown_input",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="markdown_input", stuff=markdown_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose report with MarkdownText field from MarkdownText",
                "inputs": {"markdown_input": "Text"},
                "construct": ContentConversionTestData.MARKDOWN_TO_MARKDOWN_CONSTRUCT,
                "output": "compose_structured_test.ReportWithMarkdown",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_markdown_to_markdown",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "ReportWithMarkdown"

        report = main_stuff.content
        # The markdown_content field is MarkdownText, so the subclass object should be kept
        assert type(report.markdown_content).__name__ == "MarkdownText"  # type: ignore[attr-defined]
        assert report.markdown_content.text == "# Markdown Title\n\nSome content here."  # type: ignore[attr-defined]
        assert report.markdown_content.format_type == "markdown"  # type: ignore[attr-defined]
        assert report.summary == "Plain text summary"  # type: ignore[attr-defined]

        pretty_print(report, title="ReportWithMarkdown - MarkdownText to MarkdownText")

    async def test_compose_list_content_to_list_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that ListContent items are extracted when target field expects list[X]."""
        load_test_library(test_library_path)

        # Create working memory with ListContent containing TeamMembers
        team_members = ListContent[TeamMember](
            items=[
                TeamMember(name="Alice", role="Engineer"),
                TeamMember(name="Bob", role="Designer"),
                TeamMember(name="Charlie", role="Manager"),
            ]
        )
        members_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=team_members,
            name="team_members",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="team_members", stuff=members_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose team report with list[TeamMember] field from ListContent",
                "inputs": {"team_members": "Text"},
                "construct": ContentConversionTestData.LIST_TO_LIST_CONSTRUCT,
                "output": "compose_structured_test.TeamReport",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_list_to_list",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "TeamReport"

        report = main_stuff.content
        # The members field is list[TeamMember], so items should be extracted
        assert isinstance(report.members, list)  # type: ignore[attr-defined]
        assert len(report.members) == 3  # type: ignore[attr-defined]
        assert report.members[0].name == "Alice"  # type: ignore[attr-defined]
        assert report.members[1].name == "Bob"  # type: ignore[attr-defined]
        assert report.members[2].role == "Manager"  # type: ignore[attr-defined]
        assert report.team_name == "Engineering Team"  # type: ignore[attr-defined]

        pretty_print(report, title="TeamReport - ListContent to list[TeamMember]")

    async def test_compose_list_content_to_list_content_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        test_library_path: list[Path],
    ):
        """Test that ListContent is kept as-is when target field expects ListContent."""
        load_test_library(test_library_path)

        # Create working memory with ListContent containing TeamMembers
        team_members = ListContent[TeamMember](
            items=[
                TeamMember(name="Alice", role="Engineer"),
                TeamMember(name="Bob", role="Designer"),
            ]
        )
        members_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=team_members,
            name="team_members",
        )

        working_memory = WorkingMemory()
        working_memory.add_new_stuff(name="team_members", stuff=members_stuff)

        pipe_compose_blueprint = PipeComposeBlueprint.model_validate(
            {
                "description": "Compose team report with ListContent field from ListContent",
                "inputs": {"team_members": "Text"},
                "construct": ContentConversionTestData.LIST_TO_LIST_CONTENT_CONSTRUCT,
                "output": "compose_structured_test.TeamReportWithListContent",
            }
        )

        pipe = PipeFactory[PipeCompose].make_from_blueprint(
            domain_code="compose_structured_test",
            pipe_code="compose_list_to_list_content",
            blueprint=pipe_compose_blueprint,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        main_stuff = pipe_output.main_stuff
        assert main_stuff is not None
        assert type(main_stuff.content).__name__ == "TeamReportWithListContent"

        report = main_stuff.content
        # The members_list field is ListContent, so the object should be kept
        assert isinstance(report.members_list, ListContent)  # type: ignore[attr-defined]
        assert report.members_list.nb_items == 2  # type: ignore[attr-defined]
        assert report.members_list.items[0].name == "Alice"  # type: ignore[attr-defined]
        assert report.members_list.items[1].role == "Designer"  # type: ignore[attr-defined]
        assert report.team_name == "Engineering Team"  # type: ignore[attr-defined]

        pretty_print(report, title="TeamReportWithListContent - ListContent to ListContent")
