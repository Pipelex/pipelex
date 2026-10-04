"""Fakes and readings shared by the doctor's log-sink and secrets-provider row tests."""

from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log import log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path


def doctor_log_config(*, sink: str, console_log_target: ConsoleTarget = ConsoleTarget.STDERR) -> LogConfig:
    """The shipped ``[runtime.log]``, with the sink and the console target the test names."""
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate({**config_dict["runtime"]["log"], "sink": sink, "console_log_target": console_log_target})


def assert_the_fallback_console_sink_is_installed_on_stderr() -> None:
    sink = log.sink
    assert isinstance(sink, ConsoleLogSink)
    handler = sink.handler
    assert isinstance(handler, RichHandler)
    assert handler.console.file is sys.stderr


class NullLogSink(LogSink):
    """A sink whose handler drops every record."""

    @override
    def make_handler(self) -> logging.Handler:
        return logging.NullHandler()
