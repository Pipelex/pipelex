from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING

import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.error_fields import ERROR_MESSAGE_FIELD, ERROR_TYPE_FIELD, error_fields
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


class _ManifestParseError(ValueError):
    pass


class TestLogErrorFields:
    @pytest.mark.parametrize(
        ("topic", "exc", "text", "expected"),
        [
            ("the exception's own text", _ManifestParseError("line 3: expected a table"), None, ("_ManifestParseError", "line 3: expected a table")),
            (
                "the cause chain instead",
                KeyError("dep"),
                "dep: not found; git: repository not found",
                ("KeyError", "dep: not found; git: repository not found"),
            ),
            ("an exception with no text", RuntimeError(), None, ("RuntimeError", "")),
        ],
    )
    def test_the_fields_name_the_class_and_carry_the_text(self, topic: str, exc: BaseException, text: str | None, expected: tuple[str, str]) -> None:
        assert error_fields(exc=exc, text=text) == {ERROR_TYPE_FIELD: expected[0], ERROR_MESSAGE_FIELD: expected[1]}, topic

    @pytest.fixture
    def json_buffer(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, io.StringIO]]:
        """A fresh ``Log`` with the json sink installed on a buffer, torn down so the root logger is left as found."""
        caplog.set_level(logging.INFO, logger=__name__)
        config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=LogConfig.model_validate(config_dict["runtime"]["log"]))
        fresh.install_sink(JsonLogSink(stream=buffer))
        try:
            yield fresh, buffer
        finally:
            fresh.reset()

    def test_a_handled_exception_reaches_a_structured_sink_as_two_keys_and_no_traceback(self, json_buffer: tuple[Log, io.StringIO]) -> None:
        """The dotted names are nobody's attribute, so they land unprefixed, and a warning carries no exception."""
        fresh, buffer = json_buffer
        error_text = "line 3: expected a table"
        try:
            raise _ManifestParseError(error_text)
        except _ManifestParseError as exc:
            fresh.warning("The package's METHODS.toml could not be parsed", fields=error_fields(exc=exc))
        lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        own_lines = [line for line in lines if line[LOGGER_KEY] == __name__]
        assert len(own_lines) == 1
        assert own_lines[0][MESSAGE_KEY] == "The package's METHODS.toml could not be parsed"
        assert own_lines[0][ERROR_TYPE_FIELD] == "_ManifestParseError"
        assert own_lines[0][ERROR_MESSAGE_FIELD] == "line 3: expected a table"
        assert EXCEPTION_KEY not in own_lines[0]
