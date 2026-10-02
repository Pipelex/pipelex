import pytest

from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.test_extras.mthds_corpus.loader import get_entry

# The bundle is a corpus entry, not a fixture local to this test: the corpus is the single source
# for language-level `.mthds` methods, and covering `native.markdown` is exactly why the entry exists.
_FIXTURE_DIR = get_entry(name="native_markdown_inspection_report").directory


@pytest.mark.asyncio(loop_scope="class")
class TestMarkdownDryRun:
    async def test_dry_run_markdown_report_feeds_a_text_step(self):
        """The sequence's LLM step writes a Markdown report, which the next step reads as its Text input."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)

        response = await runner.execute(pipe_code="report_and_log", inputs={"notes": "Roof: two cracked tiles above the north gable."})

        assert response.state == RunState.COMPLETED
        report_stuff = response.pipe_output.working_memory.get_stuff("report")
        assert report_stuff.concept.concept_ref == "native.Markdown"
        assert type(report_stuff.content) is MarkdownContent
        assert report_stuff.as_markdown.text
        assert response.pipe_output.main_stuff.as_text.text

    async def test_dry_run_markdown_envelope_fills_a_text_input(self):
        """A Markdown input in the envelope form fills a Text input and stays a Markdown in memory."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], pipe_run_mode=PipeRunMode.DRY)
        report_source = "# Roof\n\n- two cracked tiles\n- sagging gutter"

        response = await runner.execute(pipe_code="log_report", inputs={"report": {"concept": "Markdown", "content": report_source}})

        assert response.state == RunState.COMPLETED
        report_stuff = response.pipe_output.working_memory.get_stuff("report")
        assert report_stuff.concept.concept_ref == "native.Markdown"
        assert report_stuff.content == MarkdownContent(text=report_source)
        assert response.pipe_output.main_stuff.as_text.text
