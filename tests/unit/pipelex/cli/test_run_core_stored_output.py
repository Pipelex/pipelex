from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from rich.console import Console
from rich.text import Text

from pipelex.core.stuffs import stored_value_output
from pipelex.core.stuffs.stored_value_output import load_stored_values_of_output, render_unloaded_output_markdown
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

STORED_KEY = "local/generated/0123456789abcdef/value.txt"
STORED_TEXT = "The whole report the run produced, longer than its preview.\n" * 8


def _stored_report(*, url: str = f"pipelex-storage://{STORED_KEY}") -> TextContent:
    return TextContent(
        url=url,
        size=len(STORED_TEXT.encode("utf-8")),
        mime_type="text/plain",
        preview=STORED_TEXT[:40],
    )


def _printed(renderable: object) -> str:
    console = Console(width=200, record=True)
    console.print(renderable)
    return console.export_text()


@pytest.mark.asyncio(loop_scope="class")
class TestRunCoreStoredOutput:
    async def test_a_stored_output_is_loaded_and_prints_whole(self):
        storage = InMemoryStorageProvider()
        storage.root[STORED_KEY] = STORED_TEXT.encode("utf-8")
        report = _stored_report()

        is_loaded = await load_stored_values_of_output(content=report, read_scope=None, storage_provider=storage)

        assert is_loaded
        assert report.is_loaded
        assert report.require_text() == STORED_TEXT
        assert "The whole report the run produced" in _printed(report.rendered_pretty())

    @pytest.mark.parametrize(
        ("topic", "url"),
        [
            ("the storage cannot serve it", f"pipelex-storage://{STORED_KEY}"),
            ("a local file that is gone", "/nonexistent/directory/report.txt"),
            ("a malformed data URL", "data:text/plain;base64,QQ"),
        ],
    )
    async def test_a_stored_output_that_cannot_be_loaded_prints_its_description(self, mocker: MockerFixture, topic: str, url: str):
        warning_spy = mocker.spy(stored_value_output.log, "warning")
        report = _stored_report(url=url)

        is_loaded = await load_stored_values_of_output(content=report, read_scope=None, storage_provider=InMemoryStorageProvider())

        assert not is_loaded, topic
        assert not report.is_loaded, topic
        warning_spy.assert_called_once()
        rendered = report.rendered_pretty()
        assert isinstance(rendered, Text)
        printed = _printed(rendered)
        assert "not loaded" in printed
        assert STORED_TEXT[:40] in printed
        assert "not loaded" in render_unloaded_output_markdown(content=report)
        assert not Path("/nonexistent/directory/report.txt").exists()
