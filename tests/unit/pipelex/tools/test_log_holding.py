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

    from pytest_mock import MockerFixture


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


class _RaisingOnPoisonHandler(_ListHandler):
    """Raises out of ``emit`` on one message, the way Rich raises on a line it reads as unbalanced markup."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage() == "poison":
            msg = "closing tag '[/pipe]' doesn't match any open tag"
            raise RuntimeError(msg)
        super().emit(record)


class _RaisingOnPoisonSink(_ListSink):
    def __init__(self) -> None:
        super().__init__()
        self.list_handler = _RaisingOnPoisonHandler()


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

    def test_a_held_record_the_sink_cannot_render_costs_neither_the_others_nor_the_installation(
        self, fresh_log: Log, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The sink stays installed so ``reset`` removes it, and the records after the poisoned one are replayed."""
        fresh_log.info("held first")
        fresh_log.info("poison")
        fresh_log.info("held third")
        sink = _RaisingOnPoisonSink()

        fresh_log.install_sink(sink)
        fresh_log.info("live fourth")

        assert sink.own_messages() == ["held first", "held third", "live fourth"]
        assert fresh_log.sink is sink
        assert sink.handler in logging.getLogger().handlers
        assert "Logging error" in capsys.readouterr().err
        fresh_log.reset()
        assert fresh_log.sink is None
        assert sink.handler not in logging.getLogger().handlers

    @staticmethod
    def _emit_while_both_handlers_are_on_the_root(*, mocker: MockerFixture, fresh_log: Log, message: str) -> None:
        """Widen the handoff's window deterministically: a record is emitted right before the holding handler leaves the root.

        ``install_sink`` puts the sink's handler on the root logger and then removes the holding handler; wrapping
        the removal emits a record while both are on the root, which is the interleaving a concurrent thread produces.
        """
        original_remove = logging.Logger.removeHandler

        def remove_after_emitting(logger: logging.Logger, handler: logging.Handler) -> None:
            if isinstance(handler, HoldingLogHandler):
                fresh_log.info(message)
            original_remove(logger, handler)

        mocker.patch.object(logging.Logger, "removeHandler", autospec=True, side_effect=remove_after_emitting)

    def test_a_record_emitted_while_both_handlers_are_on_the_root_is_delivered_exactly_once(self, fresh_log: Log, mocker: MockerFixture) -> None:
        fresh_log.info("held")
        sink = _ListSink()
        self._emit_while_both_handlers_are_on_the_root(mocker=mocker, fresh_log=fresh_log, message="meanwhile")

        fresh_log.install_sink(sink)
        fresh_log.info("live")

        assert sink.own_messages().count("meanwhile") == 1
        assert not any(isinstance(handler, HoldingLogHandler) for handler in logging.getLogger().handlers)

    def test_the_held_records_precede_a_record_emitted_during_the_handoff(self, fresh_log: Log, mocker: MockerFixture) -> None:
        fresh_log.info("held first")
        fresh_log.warning("held second")
        sink = _ListSink()
        self._emit_while_both_handlers_are_on_the_root(mocker=mocker, fresh_log=fresh_log, message="meanwhile")

        fresh_log.install_sink(sink)
        fresh_log.info("live")

        assert sink.own_messages() == ["held first", "held second", "meanwhile", "live"]

    def test_a_processor_runs_once_on_a_record_forwarded_during_the_handoff(self, fresh_log: Log, mocker: MockerFixture) -> None:
        sink = _ListSink()

        def count(record: logging.LogRecord) -> None:
            record.processed = getattr(record, "processed", 0) + 1

        sink.processors.append(count)
        self._emit_while_both_handlers_are_on_the_root(mocker=mocker, fresh_log=fresh_log, message="meanwhile")

        fresh_log.install_sink(sink)

        own = [record for record in sink.list_handler.records if record.name == __name__]
        assert [(record.getMessage(), getattr(record, "processed", None)) for record in own] == [("meanwhile", 1)]

    def test_a_record_that_reaches_the_holding_handler_after_the_drain_is_forwarded_to_the_sink(self) -> None:
        """A thread that picked the holding handler off the root logger just before its removal must lose nothing."""
        holding = HoldingLogHandler()
        target = _ListHandler()
        holding.handle(logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="before", args=(), exc_info=None))
        holding.release_to(handler=target)

        holding.handle(logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="late", args=(), exc_info=None))
        holding.close()
        holding.handle(logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="later still", args=(), exc_info=None))

        assert [record.getMessage() for record in target.records] == ["before", "late", "later still"]
        assert holding.held_count == 0

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
