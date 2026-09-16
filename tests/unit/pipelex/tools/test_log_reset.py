"""``Log.reset`` finishes whatever the sink's handler does when it is flushed and closed.

It runs first in the runtime's release of its process globals, so an error escaping it would skip the
rest of that release and leave the process unbootable. A closed stream stays silent, as it does for
the stdlib's own shutdown; anything else the sink raises is said on stderr and swallowed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


class _RaisingAtCloseHandler(logging.Handler):
    def __init__(self, *, error: Exception) -> None:
        super().__init__()
        self._error = error

    @override
    def emit(self, record: logging.LogRecord) -> None:
        return

    @override
    def close(self) -> None:
        raise self._error


class _RaisingAtCloseSink(LogSink):
    def __init__(self, *, error: Exception) -> None:
        super().__init__()
        self._error = error

    @override
    def make_handler(self) -> logging.Handler:
        return _RaisingAtCloseHandler(error=self._error)


class TestLogReset:
    @pytest.fixture
    def configured_log(self) -> Iterator[Log]:
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        try:
            yield fresh
        finally:
            fresh.reset()

    def test_an_error_out_of_the_sinks_close_is_said_on_stderr_and_the_reset_finishes(
        self, configured_log: Log, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sink = _RaisingAtCloseSink(error=RuntimeError("the collector is gone"))
        configured_log.install_sink(sink)

        configured_log.reset()

        assert configured_log.sink is None
        assert sink.handler not in logging.getLogger().handlers
        captured = capsys.readouterr()
        assert "_RaisingAtCloseSink" in captured.err
        assert "the collector is gone" in captured.err

    def test_a_closed_stream_stays_silent_as_it_does_for_the_stdlibs_own_shutdown(
        self, configured_log: Log, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sink = _RaisingAtCloseSink(error=ValueError("I/O operation on closed file"))
        configured_log.install_sink(sink)

        configured_log.reset()

        assert configured_log.sink is None
        assert capsys.readouterr().err == ""
