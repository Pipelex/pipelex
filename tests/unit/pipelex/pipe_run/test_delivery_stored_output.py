"""The result files a delivery writes for a run whose main output holds stored values.

On a hosted plane the delivery builds the main output from the raw working memory, where a stored text is its
reference, never loaded. The JSON file carries that reference, the shape the wire carries; the Markdown, the HTML and
the viewer are read by a person, so the delivery loads the stored values first under the run's read scope, and
describes the reference when it cannot. No main output file is ever left out for a stored value.
"""

import json
from typing import Any, cast

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex.pipe_run import delivery_executor as delivery_executor_module
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

READ_SCOPE = "org_a"
STORED_KEY = "org_a/mt_x/run_1/generated/0123456789abcdef/value.txt"
STORED_URL = f"pipelex-storage://{STORED_KEY}"
STORED_TEXT = "The whole report the run produced, line after line.\n" * 120
STORED_PREVIEW = STORED_TEXT[:60]
MAIN_STUFF_FILE_NAMES = ("main_stuff.json", "main_stuff.md", "main_stuff.html", "main_stuff_viewer.html")


def _stored_text_reference() -> dict[str, Any]:
    return {"url": STORED_URL, "size": len(STORED_TEXT.encode("utf-8")), "mime_type": "text/plain", "preview": STORED_PREVIEW}


def _text_main_stuff() -> dict[str, Any]:
    return {"stuff_code": "abc", "stuff_name": "main_stuff", "concept": "native.Text", "content": _stored_text_reference()}


def _pages_main_stuff() -> dict[str, Any]:
    page: dict[str, Any] = {"text_and_images": {"text": _stored_text_reference(), "images": []}, "page_view": None}
    return {"stuff_code": "abc", "stuff_name": "main_stuff", "concept": "native.Page", "content": [page]}


def _raw_output(mocker: MockerFixture, *, raw_main_stuff: dict[str, Any]) -> MockType:
    """A pipe output as it crosses a durable orchestrator: its working memory raw, its main stuff a stored value's reference."""
    mock_output: MockType = mocker.MagicMock()
    mock_output.tokens_usages = None
    mock_output.usage_assembly_error = None
    mock_output.pipe_io_artifacts = None
    mock_output.graph_spec = None
    mock_output.working_memory_raw = {"root": {"main_stuff": raw_main_stuff}, "aliases": {}}
    return mock_output


def _patch_storage(mocker: MockerFixture, *, holds_the_text: bool) -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider()
    if holds_the_text:
        storage.root[STORED_KEY] = STORED_TEXT.encode("utf-8")
    mocker.patch.object(delivery_executor_module, "get_storage_provider", return_value=storage)
    return storage


def _text_of(files: dict[str, Any], file_name: str) -> str:
    data: bytes = files[file_name].data
    return data.decode("utf-8")


def _references_in(value: Any) -> list[dict[str, Any]]:
    """Every stored value's reference in a JSON value, at any depth."""
    if isinstance(value, dict):
        as_dict = cast("dict[str, Any]", value)
        if as_dict.get("url") == STORED_URL:
            return [as_dict]
        return [reference for item in as_dict.values() for reference in _references_in(item)]
    if isinstance(value, list):
        as_list = cast("list[Any]", value)
        return [reference for item in as_list for reference in _references_in(item)]
    return []


@pytest.mark.asyncio(loop_scope="class")
class TestDeliveryStoredOutput:
    @pytest.mark.parametrize(
        "raw_main_stuff",
        [
            pytest.param(_text_main_stuff(), id="a_stored_text"),
            pytest.param(_pages_main_stuff(), id="pages_holding_a_stored_text"),
        ],
    )
    async def test_a_stored_main_output_delivers_every_main_stuff_file_its_json_the_reference(
        self, mocker: MockerFixture, raw_main_stuff: dict[str, Any]
    ) -> None:
        """The JSON file is the reference form; the Markdown, the HTML and the viewer read the value, loaded under the run's read scope."""
        _patch_storage(mocker, holds_the_text=True)

        files = await DeliveryExecutor().generate_result_files(_raw_output(mocker, raw_main_stuff=raw_main_stuff), read_scope=READ_SCOPE)

        for file_name in MAIN_STUFF_FILE_NAMES:
            assert file_name in files, file_name
        main_stuff_json = json.loads(_text_of(files, "main_stuff.json"))
        assert _references_in(main_stuff_json) == [_stored_text_reference()]
        assert STORED_TEXT not in _text_of(files, "main_stuff.json")
        assert STORED_TEXT.strip() in _text_of(files, "main_stuff.md")
        assert "The whole report the run produced" in _text_of(files, "main_stuff.html")
        assert "The whole report the run produced" in _text_of(files, "main_stuff_viewer.html")

    @pytest.mark.parametrize(
        ("topic", "holds_the_text", "read_scope"),
        [
            ("the storage no longer holds the value", False, READ_SCOPE),
            ("the value lies outside the run's read scope", True, "org_b"),
        ],
    )
    @pytest.mark.parametrize(
        "raw_main_stuff",
        [
            pytest.param(_text_main_stuff(), id="a_stored_text"),
            pytest.param(_pages_main_stuff(), id="pages_holding_a_stored_text"),
        ],
    )
    async def test_a_stored_value_that_cannot_be_loaded_is_described_in_every_main_stuff_file(
        self, mocker: MockerFixture, raw_main_stuff: dict[str, Any], topic: str, holds_the_text: bool, read_scope: str
    ) -> None:
        """A value the delivery cannot load is described by its reference: no file is left out, and nothing is read past the read scope."""
        _patch_storage(mocker, holds_the_text=holds_the_text)
        load_spy = mocker.spy(InMemoryStorageProvider, "load_with_metadata")
        warning_spy = mocker.spy(delivery_executor_module.log, "warning")

        files = await DeliveryExecutor().generate_result_files(_raw_output(mocker, raw_main_stuff=raw_main_stuff), read_scope=read_scope)

        for file_name in MAIN_STUFF_FILE_NAMES:
            assert file_name in files, f"{topic}: {file_name}"
        assert _references_in(json.loads(_text_of(files, "main_stuff.json"))) == [_stored_text_reference()], topic
        for file_name in ("main_stuff.md", "main_stuff.html", "main_stuff_viewer.html"):
            rendered = _text_of(files, file_name)
            assert "not loaded" in rendered, f"{topic}: {file_name}"
            assert "The whole report the run produced" in rendered, f"{topic}: {file_name}"
            assert STORED_TEXT.strip() not in rendered, f"{topic}: {file_name}"
        if read_scope != READ_SCOPE:
            load_spy.assert_not_called()
        # The delivery's own renders never meet a value it did not load: it described it instead.
        rendered_file_warnings = [
            call
            for call in warning_spy.call_args_list
            if call.args and call.args[0] == "A result file could not be rendered and was left out of the delivery"
        ]
        assert not rendered_file_warnings, topic

    async def test_an_inline_main_output_keeps_its_rendered_json(self, mocker: MockerFixture) -> None:
        """A main output holding no stored value keeps the JSON its content renders."""
        _patch_storage(mocker, holds_the_text=False)
        raw_main_stuff = {"stuff_code": "abc", "stuff_name": "main_stuff", "concept": "native.Text", "content": {"text": "short"}}

        files = await DeliveryExecutor().generate_result_files(_raw_output(mocker, raw_main_stuff=raw_main_stuff), read_scope=READ_SCOPE)

        for file_name in MAIN_STUFF_FILE_NAMES:
            assert file_name in files, file_name
        assert json.loads(_text_of(files, "main_stuff.json")) == {"text": "short"}
        assert _text_of(files, "main_stuff.md") == "short"

    async def test_a_render_meeting_a_value_never_loaded_is_logged_as_an_error(self, mocker: MockerFixture) -> None:
        """A render that still meets a value never loaded is a fault of the delivery's, logged as an error with the error, never a quiet warning."""
        _patch_storage(mocker, holds_the_text=True)
        mocker.patch.object(delivery_executor_module, "load_stored_values_of_output", new=mocker.AsyncMock(return_value=True))
        error_spy = mocker.spy(delivery_executor_module.log, "error")

        files = await DeliveryExecutor().generate_result_files(_raw_output(mocker, raw_main_stuff=_text_main_stuff()), read_scope=READ_SCOPE)

        assert "main_stuff.json" in files
        assert error_spy.call_count == 3
        for call in error_spy.call_args_list:
            assert call.kwargs["fields"]["error.type"] == "StoredValueNotLoadedError"
