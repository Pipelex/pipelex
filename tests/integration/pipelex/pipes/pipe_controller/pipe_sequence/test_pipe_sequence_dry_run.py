"""Dry run tests for PipeSequence controller with batching functionality."""

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.json_utils import load_json_list_from_path
from tests.test_pipelines.discord_newsletter import ChannelSummary, DiscordChannelUpdate


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeSequenceDryRun:
    """Test PipeSequence dry run functionality with batching."""

    async def test_discord_newsletter_dry_run_working_memory(
        self,
        request: FixtureRequest,
        pipe_run_mode: PipeRunMode,
    ) -> None:
        """Test that the Discord newsletter pipeline creates correct working memory with ListContent for batched inputs."""
        # Load the discord channel updates data from JSON
        DISCORD_EXTRACT_PATH = "tests/data/discord_newsletter/discord_sample.json"
        discord_channel_updates_data = load_json_list_from_path(DISCORD_EXTRACT_PATH)

        # Create structured DiscordChannelUpdate objects
        discord_channel_updates = ListContent[DiscordChannelUpdate](
            items=[DiscordChannelUpdate.model_validate(article_data) for article_data in discord_channel_updates_data]
        )

        # Create Stuff object for the discord channel updates list
        discord_updates_stuff = StuffFactory.make_stuff(
            concept_str="discord_newsletter.DiscordChannelUpdate", content=discord_channel_updates, name="discord_channel_updates"
        )

        # Create working memory with the discord channel updates
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=discord_updates_stuff)

        # Run the Discord newsletter pipeline in dry run mode
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code="write_discord_newsletter",
            job_metadata=JobMetadata(job_name=request.node.originalname),  # type: ignore
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Log output for debugging
        pretty_print(pipe_output, title="Discord Newsletter Dry Run Output")
        get_report_delegate().generate_report()

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # The pipeline only has one step (summarization), so the final output is ChannelSummary
        # This test is focused on verifying that batching works correctly in dry run mode
        assert pipe_output.main_stuff.concept_code == "discord_newsletter.ChannelSummary"
        if pipe_run_mode == PipeRunMode.DRY:
            assert isinstance(pipe_output.main_stuff.content, ListContent)

        # Verify working memory structure
        final_working_memory: WorkingMemory = pipe_output.working_memory

        # Check that discord_channel_updates was created as ListContent
        discord_updates_stuff_final = final_working_memory.get_stuff("discord_channel_updates")
        assert discord_updates_stuff_final.concept_code == "discord_newsletter.DiscordChannelUpdate"

        if pipe_run_mode == PipeRunMode.DRY:
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
            assert channel_summaries_stuff.concept_code == "discord_newsletter.ChannelSummary"

            # Verify channel_summaries is also a ListContent with multiple ChannelSummary items
            channel_summaries_list: ListContent[ChannelSummary] = channel_summaries_stuff.as_list_of_fixed_content_type(item_type=ChannelSummary)
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

            print("✅ Successfully verified dry run working memory:")
            print(f"   - discord_channel_updates: ListContent with {len(discord_updates_list.items)} items")
            print(f"   - channel_summaries: ListContent with {len(channel_summaries_list.items)} items")
            print(f"   - Final output: ChannelSummary list with concept code {pipe_output.main_stuff.concept_code}")
