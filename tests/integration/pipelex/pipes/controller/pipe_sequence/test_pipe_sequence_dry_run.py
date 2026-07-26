from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.method_hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.json_utils import load_json_list_from_path
from tests.integration.pipelex.pipes.controller.pipe_sequence.discord_newsletter import ChannelSummary, DiscordChannelUpdate

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeSequenceDryRun:
    async def test_discord_newsletter(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that the Discord newsletter pipeline creates correct working memory with ListContent for batched inputs."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_sequence")])
        # Load the discord channel updates data from JSON
        discord_channel_updates_data = load_json_list_from_path(path=Path("tests/data/discord_newsletter/discord_sample.json"))

        # Create structured DiscordChannelUpdate objects
        discord_channel_updates = ListContent[DiscordChannelUpdate](
            items=[DiscordChannelUpdate.model_validate(article_data) for article_data in discord_channel_updates_data],
        )

        # Create Stuff object for the discord channel updates list
        discord_updates_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DiscordChannelUpdate",
                domain_code="discord_newsletter",
                description="Lorem Ipsum",
                structure_class_name="DiscordChannelUpdate",
            ),
            content=discord_channel_updates,
            name="discord_channel_updates",
        )

        # Create working memory with the discord channel updates
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=discord_updates_stuff)
        # Run the Discord newsletter pipeline in dry run mode
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="write_discord_newsletter"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        # Log output for debugging
        pretty_print(pipe_output, title="Discord Newsletter Dry Run Output")

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # The pipeline only has one step (summarization), so the final output is ChannelSummary
        # This test is focused on verifying that batching works correctly in dry run mode
        assert pipe_output.main_stuff.concept.code == "HtmlNewsletter"
        assert pipe_output.main_stuff.concept.domain_code == "discord_newsletter"

        # Verify working memory structure
        final_working_memory: WorkingMemory = pipe_output.working_memory

        # Check that discord_channel_updates was created as ListContent
        discord_updates_stuff_final = final_working_memory.get_stuff("discord_channel_updates")
        assert discord_updates_stuff_final.concept.code == "DiscordChannelUpdate"
        assert discord_updates_stuff_final.concept.domain_code == "discord_newsletter"

        # The key assertion: verify it's a ListContent with multiple items
        discord_updates_list = discord_updates_stuff_final.as_list_of_fixed_content_type(item_type=DiscordChannelUpdate)
        assert isinstance(discord_updates_list, ListContent)
        assert len(discord_updates_list.items) > 1, "Should have multiple items for batching"

        # Verify each discord update item
        for i, update in enumerate(discord_updates_list.items):
            assert isinstance(update, DiscordChannelUpdate), f"Update {i} should be DiscordChannelUpdate"
            assert len(update.name) > 0, f"Update {i} should have a non-empty channel name"

        # Check that channel_summaries was created as ListContent (result of batched operation)
        channel_summaries_stuff: Stuff | None = final_working_memory.get_optional_stuff("channel_summaries")
        assert channel_summaries_stuff is not None, "channel_summaries should be in working memory"
        assert channel_summaries_stuff.concept.code == "ChannelSummary"
        assert channel_summaries_stuff.concept.domain_code == "discord_newsletter"
        assert isinstance(channel_summaries_stuff, Stuff), "ChannelSurrmary Stuff is not a Stuff"

        # Verify channel_summaries is also a ListContent with multiple ChannelSummary items
        channel_summaries_list = channel_summaries_stuff.as_list_of_fixed_content_type(item_type=ChannelSummary)

        pretty_print(channel_summaries_stuff, title="Channel Summaries Stuff")
        pretty_print(channel_summaries_list, title="Channel Summaries List")
        assert isinstance(channel_summaries_list, ListContent)
        assert len(channel_summaries_list.items) > 1, "Should have multiple ChannelSummary items from batch processing"

        # Verify each summary item (these should be proper ChannelSummary objects from the LLM mock)
        for i, summary in enumerate(channel_summaries_list.items):
            assert isinstance(summary, ChannelSummary), f"Summary {i} should be ChannelSummary"
            assert len(summary.channel_name) > 0, f"Summary {i} should have a non-empty channel name"
            assert isinstance(summary.summary_items, list), f"Summary {i} should have a list of summary items"

        # Verify that the number of summaries matches the number of original channel updates
        assert len(channel_summaries_list.items) == len(discord_updates_list.items), (
            "Number of summaries should match number of original channel updates"
        )

        log.info("✅ Successfully verified dry run working memory:")
        log.info(f"   - discord_channel_updates: ListContent with {len(discord_updates_list.items)} items")
        log.info(f"   - channel_summaries: ListContent with {len(channel_summaries_list.items)} items")
        log.info(f"   - Final output: ChannelSummary list with concept code {pipe_output.main_stuff.concept.code}")
