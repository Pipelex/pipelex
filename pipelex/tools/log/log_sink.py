"""Where the records go: the sink seam.

A sink owns one stdlib handler on the root logger and everything about how a record leaves the
process: the stream, the wire shape, the exporter. Which sink a process runs is a registrar
capability selected by ``[runtime.log] sink``, exactly as the storage and secrets providers are: the
built-in plugin registers ``json``, ``console`` and ``otlp`` under open string tokens, and an external
plugin registers its own. This module holds what every sink shares, the base class with its processor
slot and the stream resolution, and names no sink.
"""

from __future__ import annotations

import json
import logging
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from typing_extensions import override

from pipelex.system.console_target import ConsoleTarget

if TYPE_CHECKING:
    from typing import TextIO

# A processor edits a record in place before the sink renders it; redaction is the intended one. It
# runs on the sink's own handler, once per record, so a handler another integration attached to the
# root logger sees the record as the processors left it only if it runs after this one.
LogRecordProcessor = Callable[[logging.LogRecord], None]


class LogSinkMethod(StrEnum):
    """The tokens the built-in plugin registers. An external plugin registers its own string."""

    JSON = "json"
    CONSOLE = "console"
    OTLP = "otlp"


class _ProcessorFilter(logging.Filter):
    """Runs the sink's processors over each record before the handler formats it, and never drops one."""

    def __init__(self, processors: list[LogRecordProcessor]):
        super().__init__()
        self._processors = processors

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        for processor in self._processors:
            processor(record)
        return True


class LogSink(ABC):
    """One destination for the records the root logger emits.

    A subclass builds the stdlib handler in ``make_handler``, and does whatever heavy import it needs
    there rather than at module load, so that selecting a sink is what pays for its dependency. The
    base attaches the processor slot to that handler and hands the same handler back on every read.
    """

    def __init__(self) -> None:
        self.processors: list[LogRecordProcessor] = []
        self._handler: logging.Handler | None = None

    @abstractmethod
    def make_handler(self) -> logging.Handler:
        """Build the handler this sink installs on the root logger. Called once, at install."""

    @property
    def handler(self) -> logging.Handler:
        """The sink's handler, built on first read with the processors wired in front of it."""
        if self._handler is None:
            handler = self.make_handler()
            handler.addFilter(_ProcessorFilter(self.processors))
            self._handler = handler
        return self._handler

    def redirect_to_stderr(self) -> None:
        """Point a sink that writes to a process stream at stderr; a sink that does not ignores the call."""
        return


def stream_for_target(*, target: ConsoleTarget) -> TextIO:
    """The process stream a target names, read at call time so a redirected stream is the one used."""
    match target:
        case ConsoleTarget.STDOUT:
            return sys.stdout
        case ConsoleTarget.STDERR:
            return sys.stderr
        case ConsoleTarget.FILE:
            msg = f"A log sink cannot write to the console target '{target}': choose stdout or stderr."
            raise ValueError(msg)


def json_fallback(value: Any) -> Any:  # kw-only: ignore — json.dumps calls its ``default`` positionally
    """What ``json.dumps`` writes for a value it does not know: a model's JSON dump, anything else as text."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return str(value)


def render_json(*, value: Any) -> str:
    """Serialize one value for a wire sink without ever raising.

    A model dumps in JSON mode and an unknown object becomes its text. A value ``json`` refuses
    outright, a circular reference or a mapping with a non-string key, is written as its ``repr``
    instead: a sink must render every record it is handed, and a serialization failure is a fact about
    the value, never a reason to lose the line.
    """
    try:
        return json.dumps(value, ensure_ascii=False, default=json_fallback)
    except (TypeError, ValueError):
        return json.dumps(repr(value), ensure_ascii=False)
