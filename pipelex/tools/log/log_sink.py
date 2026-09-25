"""Where the records go: the sink seam.

A sink owns one stdlib handler on the root logger and everything about how a record leaves the
process: the stream, the wire shape, the exporter. Which sink a process runs is a registrar
capability selected by ``[runtime.log] sink``, exactly as the storage and secrets providers are: the
built-in plugin registers ``json``, ``console`` and ``otlp`` under open string tokens, and an external
plugin registers its own. This module holds what every sink shares, the base class with its processor
slot and the stream resolution, and names no sink.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel
from typing_extensions import override

from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_fields import UNSCRUBBED_MARK

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

# JSON has no spelling for a float that is not a number: ``json.dumps`` writes the bare tokens ``NaN``
# and ``Infinity`` by default, which a strict parser refuses line and all. A wire sink writes these
# strings in their place.
NAN_TEXT = "NaN"
POSITIVE_INFINITY_TEXT = "Infinity"
NEGATIVE_INFINITY_TEXT = "-Infinity"

# A processor edits a record in place before the sink renders it; redaction is the intended one. It
# runs on the sink's own handler, once per record, and on the original record rather than a copy, so a
# handler another integration attached to the root logger sees the record as the processors left it
# when it runs after this one, and as the call made it when it runs before. In place is deliberate:
# what the processors do is remove what must not leave the process, and a copy would hand every other
# handler the secret the sink was spared.
LogRecordProcessor = Callable[[logging.LogRecord], None]


class LogSinkMethod(StrEnum):
    """The tokens the built-in plugin registers. An external plugin registers its own string."""

    JSON = "json"
    CONSOLE = "console"
    OTLP = "otlp"


class ProcessorFilter(logging.Filter):
    """Runs the sink's processors over each record before the handler formats it, and drops only what one asks it to.

    The stdlib runs a handler's filters outside any ``try``, so a processor that raised would raise out
    of the ``log.<level>(...)`` call that emitted the record, against the promise that a log call never
    raises. Each processor is therefore guarded on its own: what it raises is reported on stderr, the
    processors after it still run, and the record is handed to the handler all the same. The report
    names the processor and the type of what it raised, and withholds the exception's text and
    traceback, which the handler's ``handleError`` would have printed: a processor fails on the record's
    own values, so its exception is where they end up, the secret the redaction was removing among them.
    The reporter is guarded too, since a closed stderr makes it raise. A processor that fails costs that
    record its processing, never the call and never the line; a processor that must not hand on what it
    failed to process, the redaction, strips the record itself before it raises, and where even the
    stripping failed it leaves the mark that has this filter drop the record instead.
    """

    def __init__(self, *, processors: list[LogRecordProcessor]):
        super().__init__()
        self._processors = processors

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        for processor in self._processors:
            try:
                processor(record)
            except Exception as exc:  # ruff: ignore[blind-except]
                with contextlib.suppress(Exception):
                    _report_processor_failure(processor=processor, exc=exc)
        # A processor that must not hand on what it failed to process says so by leaving the mark on the
        # record, and the record is dropped rather than emitted. It is read out of the record's own
        # dictionary, so finding out costs no call and no frame: this runs where a stack that has run
        # out is the likeliest reason a processor failed in the first place.
        return UNSCRUBBED_MARK not in record.__dict__


def _report_processor_failure(*, processor: LogRecordProcessor, exc: Exception) -> None:
    """Write the stdlib's logging-error banner with the processor and the exception type, when the stdlib would have reported at all."""
    if not logging.raiseExceptions or not sys.stderr:
        return
    processor_name = getattr(processor, "__qualname__", type(processor).__qualname__)
    sys.stderr.write(
        f"--- Logging error ---\nThe log record processor {processor_name} raised {type(exc).__name__}, and the record was handed on "
        "without it. The exception's text is withheld, since it may carry what the processor was removing.\n"
    )


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
            handler.addFilter(ProcessorFilter(processors=self.processors))
            self._handler = handler
        return self._handler

    def discard_handler(self) -> None:
        """Forget the handler built for an install, so a sink object installed again builds a fresh one.

        A teardown closes the handler, and a close is terminal for a sink that really releases what it
        writes to: a file sink closes its file there. Handing the same handler back at the next install
        would install a sink that accepts every record, runs every filter and drops the lot on the floor,
        with nothing raised to say so. The fresh handler also gets a fresh processor filter, reading
        whatever ``processors`` holds at that install rather than the list the first one closed over.

        A fresh handler is only as live as what ``make_handler`` builds it on. A sink that opens its
        target there comes back whole; one that was handed its target built, and whose close released
        it, cannot, and says so from ``make_handler`` rather than build a handler on the dead target:
        the ``otlp`` sink, whose close shuts down the provider and the processor it was constructed
        with, is that case.
        """
        self._handler = None

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
    """What ``json.dumps`` writes for a value it does not know: a model's JSON dump, anything else as text.

    A model's dump is spelled the way a value handed in directly is. ``model_dump(mode="json")`` returns a
    plain mapping that still holds the Python float, pydantic's own spelling of a non-finite one applying
    only where pydantic writes the JSON text itself, so a ``NaN`` nested in a model would reach ``json``
    under ``allow_nan=False`` and cost the whole payload its structure. Spelled here, it costs that one
    float its type and nothing else anything.
    """
    if isinstance(value, BaseModel):
        return spell_non_finite(value=value.model_dump(mode="json"))
    return str(value)


def spell_non_finite(*, value: Any) -> Any:
    """The value with every non-finite float, at any depth, replaced by the string JSON can carry.

    A ``NaN`` becomes ``"NaN"``, an infinity ``"Infinity"`` or ``"-Infinity"``, inside a mapping or a
    sequence as at the top, and everything else is returned as it was, a bool included since a bool
    is never a float here. A tuple comes back as a list, which is what JSON would have made of it. A
    container that contains itself is returned as it is, for ``json`` to refuse the way it always did.
    """
    return _spell_non_finite(value=value, open_containers=set())


def _spell_non_finite(*, value: Any, open_containers: set[int]) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return NAN_TEXT
        if math.isinf(value):
            return POSITIVE_INFINITY_TEXT if value > 0 else NEGATIVE_INFINITY_TEXT
        return value
    container_id = id(value)
    if container_id in open_containers:
        return value
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        open_containers.add(container_id)
        try:
            return {key: _spell_non_finite(value=item, open_containers=open_containers) for key, item in mapping.items()}
        finally:
            open_containers.discard(container_id)
    if isinstance(value, (list, tuple)):
        sequence = cast("Sequence[Any]", value)
        open_containers.add(container_id)
        try:
            return [_spell_non_finite(value=item, open_containers=open_containers) for item in sequence]
        finally:
            open_containers.discard(container_id)
    return value


def render_json(*, value: Any) -> str:
    """Serialize one value for a wire sink without ever raising, and never as anything but JSON.

    A model dumps in JSON mode and an unknown object becomes its text; a non-finite float is spelled
    as the string ``"NaN"``, ``"Infinity"`` or ``"-Infinity"`` rather than the bare token ``json``
    would write. A value ``json`` refuses outright, a circular reference or a mapping with a non-string
    key, is written as its ``repr`` instead: a sink must render every record it is handed, and a
    serialization failure is a fact about the value, never a reason to lose the line.
    """
    try:
        return json.dumps(spell_non_finite(value=value), ensure_ascii=False, allow_nan=False, default=json_fallback)
    except (TypeError, ValueError):
        return json.dumps(repr(value), ensure_ascii=False)
