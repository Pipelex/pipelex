import pytest
from pytest_mock import MockerFixture
from rich.console import Console
from rich.text import Text

from pipelex.cli.commands.run._run_core import _load_stored_values_of_output  # pyright: ignore[reportPrivateUsage]
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

STORED_KEY = "local/generated/0123456789abcdef/value.txt"
STORED_TEXT = "The whole report the run produced, longer than its preview.\n" * 8


def _stored_report() -> TextContent:
    return TextContent(
        url=f"pipelex-storage://{STORED_KEY}",
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
    async def test_a_stored_output_is_loaded_and_prints_whole(self, mocker: MockerFixture):
        storage = InMemoryStorageProvider()
        storage.root[STORED_KEY] = STORED_TEXT.encode("utf-8")
        mocker.patch("pipelex.cli.commands.run._run_core.get_storage_provider", return_value=storage)
        report = _stored_report()

        await _load_stored_values_of_output(content=report)

        assert report.is_loaded
        assert report.require_text() == STORED_TEXT
        assert "The whole report the run produced" in _printed(report.rendered_pretty())

    async def test_a_stored_output_the_storage_cannot_serve_prints_its_description(self, mocker: MockerFixture):
        mocker.patch("pipelex.cli.commands.run._run_core.get_storage_provider", return_value=InMemoryStorageProvider())
        warning_spy = mocker.patch("pipelex.cli.commands.run._run_core.log.warning")
        report = _stored_report()

        await _load_stored_values_of_output(content=report)

        assert not report.is_loaded
        warning_spy.assert_called_once()
        rendered = report.rendered_pretty()
        assert isinstance(rendered, Text)
        printed = _printed(rendered)
        assert "not loaded" in printed
        assert STORED_TEXT[:40] in printed
