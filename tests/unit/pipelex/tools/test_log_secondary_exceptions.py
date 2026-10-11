"""A handled exception that sits beside a payload-bearing one writes none of that payload to a structured sink.

Two shapes, each at a real call site, the records going the whole way to the ``json`` sink's line: a cleanup failing
while a primary ``ValidationError`` propagates, whose traceback would carry the primary's text through Python's
implicit chaining, and a ``ValidationError`` the code swallows, whose own text quotes the values it refused.
"""

from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.runtime_boot import RuntimeBoot
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.error_fields import ERROR_MESSAGE_FIELD, ERROR_TYPE_FIELD
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

# A value no secret pattern matches, so the redaction never hides it and only the call site's own rule can keep it out.
_PAYLOAD = "confidential-patient-diagnosis"


class _RunInputs(BaseModel):
    patient_age: int


def _lines_of(*, buffer: io.StringIO, logger_name: str) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return [line for line in lines if line[LOGGER_KEY] == logger_name]


class TestSecondaryExceptionsCarryNoPayload:
    @pytest.fixture
    def json_buffer(self, caplog: pytest.LogCaptureFixture) -> Iterator[io.StringIO]:
        """The json sink installed on a buffer through a fresh ``Log``, torn down so the root logger is left as found."""
        caplog.set_level(logging.INFO, logger="pipelex")
        config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=LogConfig.model_validate(config_dict["runtime"]["log"]))
        fresh.install_sink(JsonLogSink(stream=buffer))
        try:
            yield buffer
        finally:
            fresh.reset()

    def test_a_cleanup_failing_while_a_validation_error_propagates_writes_no_payload(self, json_buffer: io.StringIO, mocker: MockerFixture) -> None:
        """The plugin teardown callbacks of a failed boot run while the boot error propagates, and Python chains it onto theirs.

        Logged with its traceback, a failing callback's record carried the boot error's text in its ``exception`` key,
        and a ``ValidationError``'s text quotes the value it refused.
        """

        def failing_callback() -> None:
            msg = "the worker pool was already closed"
            raise RuntimeError(msg)

        boot = object.__new__(RuntimeBoot)
        boot._plugin_registrar = mocker.Mock(teardown_callbacks=[failing_callback])  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]

        primary_text = ""
        try:
            _RunInputs.model_validate({"patient_age": _PAYLOAD})
        except ValidationError as primary:
            primary_text = str(primary)
            # As `make()`'s handler does: the release runs inside the `except` that holds the boot error.
            boot._teardown_plugin_callbacks()  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
        assert _PAYLOAD in primary_text

        raw = json_buffer.getvalue()
        assert _PAYLOAD not in raw
        (line,) = _lines_of(buffer=json_buffer, logger_name="pipelex.runtime_boot")
        assert line[MESSAGE_KEY] == "A plugin teardown callback failed, and the remaining callbacks still run"
        assert line[ERROR_TYPE_FIELD] == "RuntimeError"
        assert line[ERROR_MESSAGE_FIELD] == "the worker pool was already closed"
        assert line["callback_name"].endswith("failing_callback")
        assert EXCEPTION_KEY not in line

    def test_a_swallowed_validation_error_writes_none_of_the_values_it_refused(self, json_buffer: io.StringIO) -> None:
        """A malformed absence record is treated as missing, and its error used to reach every sink as its full text."""
        malformed_record = {"variable_name": "diagnosis", "kind": _PAYLOAD, "reason": {"note": _PAYLOAD}}

        absence = DeliveryExecutor._get_raw_main_absence(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            working_memory_raw={"absences": {MAIN_STUFF_NAME: malformed_record}}
        )

        assert absence is None
        raw = json_buffer.getvalue()
        assert _PAYLOAD not in raw
        (line,) = _lines_of(buffer=json_buffer, logger_name="pipelex.pipe_run.delivery_executor")
        assert line[MESSAGE_KEY] == "The absence record of the main output is malformed"
        assert line[ERROR_TYPE_FIELD] == "ValidationError"
        assert line[ERROR_MESSAGE_FIELD].startswith("kind: Input should be ")
        assert "reason: Input should be a valid string" in line[ERROR_MESSAGE_FIELD]
        assert EXCEPTION_KEY not in line
