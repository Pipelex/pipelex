"""Records emitted between ``log.configure`` and ``log.install_sink`` are held and replayed, in order, through the sink.

A boot that dies before its sink arrives closes the holding handler, and what it held gets the
stdlib's last-resort handling: a warning or worse reaches stderr, an info is dropped.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_holding import HOLDING_CAPACITY, HoldingLogHandler
from pipelex.tools.log.log_sink import LogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _ListSink(LogSink):
    def __init__(self) -> None:
        super().__init__()
        self.list_handler = _ListHandler()

    @override
    def make_handler(self) -> logging.Handler:
        return self.list_handler

    def own_messages(self) -> list[str]:
        return [record.getMessage() for record in self.list_handler.records if record.name == __name__]


class TestHoldingLogHandler:
    @pytest.fixture
    def fresh_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[Log]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        try:
            yield fresh
        finally:
            fresh.reset()

    def test_records_held_since_configure_are_replayed_through_the_sink_in_order(self, fresh_log: Log) -> None:
        fresh_log.info("held first")
        fresh_log.warning("held second")
        sink = _ListSink()

        fresh_log.install_sink(sink)
        fresh_log.info("live third")

        assert sink.own_messages() == ["held first", "held second", "live third"]
        assert fresh_log.sink is sink
        assert sink.handler in logging.getLogger().handlers
        assert not any(isinstance(handler, HoldingLogHandler) for handler in logging.getLogger().handlers)

    def test_a_processor_edits_the_replayed_and_the_live_records_alike(self, fresh_log: Log) -> None:
        fresh_log.info("held")
        sink = _ListSink()

        def stamp(record: logging.LogRecord) -> None:
            record.stamped = True

        sink.processors.append(stamp)
        fresh_log.install_sink(sink)
        fresh_log.info("live")

        own = [record for record in sink.list_handler.records if record.name == __name__]
        assert [getattr(record, "stamped", None) for record in own] == [True, True]

    def test_without_a_sink_a_held_warning_reaches_stderr_at_reset_and_an_info_is_dropped(
        self, fresh_log: Log, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The failed-boot path: ``reset`` closes the holding handler and the stdlib's last resort speaks."""
        fresh_log.info("an info that goes nowhere")
        fresh_log.warning("a warning that must be seen")

        fresh_log.reset()

        captured = capsys.readouterr()
        assert "a warning that must be seen" in captured.err
        assert "an info that goes nowhere" not in captured.err

    def test_install_sink_before_configure_and_a_second_sink_are_refused(self) -> None:
        fresh = Log()
        with pytest.raises(RuntimeError, match="not configured"):
            fresh.install_sink(_ListSink())
        fresh.configure(log_config=_package_log_config())
        try:
            fresh.install_sink(_ListSink())
            with pytest.raises(RuntimeError, match="already installed"):
                fresh.install_sink(_ListSink())
        finally:
            fresh.reset()

    def test_the_holding_handler_keeps_the_newest_records_up_to_its_capacity(self) -> None:
        holding = HoldingLogHandler()
        for index in range(HOLDING_CAPACITY + 5):
            holding.handle(logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg=str(index), args=(), exc_info=None))

        assert holding.held_count == HOLDING_CAPACITY
        target = _ListHandler()
        holding.release_to(handler=target)
        assert holding.held_count == 0
        assert target.records[0].getMessage() == "5"
        assert target.records[-1].getMessage() == str(HOLDING_CAPACITY + 4)
