"""The handler that holds records between ``log.configure`` and the sink's arrival.

Logging is configured as soon as the configuration is read, and the sink is a capability the plugin
discovery hands over a little later in the boot. The records emitted in between are held here, in
order, and replayed through the sink's handler the moment it is installed, so a boot's own lines are
rendered by the sink the configuration chose rather than dropped or written in a shape nothing chose.
A boot that dies before a sink arrives closes this handler, and what it still holds gets the stdlib's
last-resort treatment: a warning or worse reaches stderr and the rest is dropped, exactly as a record
emitted before ``configure`` would be.
"""

from __future__ import annotations

import logging

from typing_extensions import override

# The most records held at once; beyond it the oldest are dropped, so a process that configures
# logging and never installs a sink cannot grow without bound. A boot holds a few dozen lines.
HOLDING_CAPACITY = 1000

# The attribute a forwarded record carries once the sink's handler has handled it, so the same record
# reaching that handler again through the root logger is rejected. The underscore is a convention and
# nothing more: a fresh record does not carry the name, so nothing in the stdlib stops a caller's
# ``extra`` from spelling it and having its own record rejected from every sink. What stops that is
# ``attach_log_record_extra``, which counts the mark among the names a record owns and carries such an
# entry under the ``field_`` prefix, exactly as it does for ``message`` and ``asctime``.
FORWARDED_MARK = "_pipelex_forwarded"


class ForwardedRecordFilter(logging.Filter):
    """Rejects a record the holding handler already forwarded to this handler.

    While the sink's handler and the holding handler are both on the root logger, a record reaches the
    holding handler first, which forwards it and marks it; this filter is what stops the root logger's
    own delivery of the same record right after. It sits ahead of every other filter on the handler,
    so the sink's processors never run on a record it rejects, and it stays installed: after the
    handoff no record is marked again, and a thread that read the root's handler list mid-handoff
    can still be on its way.
    """

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, FORWARDED_MARK, False)


def _deliver(*, handler: logging.Handler, record: logging.LogRecord) -> None:
    """Hand one record to the sink's handler the way the root logger would have.

    ``Logger.callHandlers`` is what checks a handler's level; ``Handler.handle`` does not, so a replay
    or a forward that called it alone would deliver what the live path withholds. And a record the
    handler cannot render gets the stdlib's own recovery, ``handleError``, rather than raising out of
    the log call that emitted it.
    """
    if record.levelno < handler.level:
        return
    try:
        handler.handle(record)
    except Exception:  # ruff: ignore[blind-except]
        handler.handleError(record)


class HoldingLogHandler(logging.Handler):
    """Holds every record it is handed until a sink's handler takes them over, then forwards to that handler."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self._held: list[logging.LogRecord] = []
        self._released_to: logging.Handler | None = None

    @property
    def held_count(self) -> int:
        return len(self._held)

    @override
    def emit(self, record: logging.LogRecord) -> None:
        # ``handle`` holds this handler's lock here, the lock ``release_to`` drains under, so a record
        # arrives either before the drain and is held, or after it and is forwarded to the handler
        # that took the held ones: never into a list nobody reads again. The mark goes on after the
        # forward, so the forward passes the handler's own guard and the root logger's delivery of
        # the same record, when the sink's handler is on the root too, does not.
        if self._released_to is not None:
            _deliver(handler=self._released_to, record=record)
            setattr(record, FORWARDED_MARK, True)
            return
        if len(self._held) >= HOLDING_CAPACITY:
            del self._held[0]
        self._held.append(record)

    def release_to(self, *, handler: logging.Handler) -> None:
        """Hand every held record to the handler, in the order they were emitted, and forward to it whatever arrives after.

        One record the handler cannot render, a line Rich reads as unbalanced markup for one, gets the
        stdlib's own recovery, ``handleError``, and costs none of the records after it.
        """
        self.acquire()
        try:
            held, self._held = self._held, []
            self._released_to = handler
            for record in held:
                _deliver(handler=handler, record=record)
        finally:
            self.release()

    @override
    def close(self) -> None:
        """Give what is still held the stdlib's last-resort handling: a warning or worse reaches stderr."""
        self.acquire()
        try:
            held, self._held = self._held, []
        finally:
            self.release()
        last_resort = logging.lastResort
        if last_resort is not None:
            for record in held:
                if record.levelno >= last_resort.level:
                    last_resort.handle(record)
        super().close()
