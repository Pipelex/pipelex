"""The handler that holds records between ``log.configure`` and the sink's arrival.

Logging is configured as soon as the configuration is read, and the sink is a capability the plugin
discovery hands over a little later in the boot. The records emitted in between are held here, in
order, and replayed through the sink's handler the moment it is installed, so a boot's own lines are
rendered by the sink the configuration chose rather than dropped or written in a shape nothing chose.
A boot that dies before a sink arrives closes this handler, and what it still holds reaches stderr
through the stdlib's last resort — every record of it, since the root logger's level already admitted
them and that level came from the configuration, so each held line is one this process was asked to
show. A boot that failed is when that trail is worth most, and the redaction the sink would have run
over each of those records runs over it on that path too.
"""

from __future__ import annotations

import logging

from typing_extensions import override

from pipelex.tools.log.log_fields import FORWARDED_MARK

# The most records held at once; beyond it the oldest are dropped, so a process that configures
# logging and never installs a sink cannot grow without bound. A boot holds a few dozen lines.
HOLDING_CAPACITY = 1000


class ForwardedRecordFilter(logging.Filter):
    """Rejects a record the holding handler already forwarded to this handler.

    While the sink's handler and the holding handler are both on the root logger, a record reaches the
    holding handler first, which forwards it and marks it; this filter is what stops the root logger's
    own delivery of the same record right after. It sits ahead of every other filter on the handler,
    so the sink's processors never run on a record it rejects, and it stays installed: after the
    handoff no record is marked again, and a thread that read the root's handler list mid-handoff
    can still be on its way.

    The mark is only ever ours, and that is a property of the attachment rather than of the spelling:
    the name is reserved in ``log_fields``, so a caller's field spelling it is carried under a prefix
    and cannot make this filter drop a record nobody delivered.
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
    """Holds every record it is handed until a sink's handler takes them over, then forwards to that handler.

    ``last_resort_filter`` is what a held record passes through on its way to the stdlib's last resort,
    when the handler closes with records still held: the redaction a sink's handler would have run over
    it, behind the same guard. A record it rejects is not written. It runs there and nowhere else, since
    a record released to a sink meets the sink's own processors, and a second pass would escape its
    control characters twice.
    """

    def __init__(self, *, last_resort_filter: logging.Filter | None = None) -> None:
        super().__init__(level=logging.NOTSET)
        self._held: list[logging.LogRecord] = []
        self._released_to: logging.Handler | None = None
        self._last_resort_filter = last_resort_filter

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

        A drained record is marked after its delivery exactly as a forwarded one is, and for the same
        reason: a thread that read the root logger's handler list before the handoff can still reach the
        sink's handler carrying a record this drain has already delivered, and the mark is the only thing
        that tells the handler's guard so.
        """
        self.acquire()
        try:
            held, self._held = self._held, []
            self._released_to = handler
            for record in held:
                _deliver(handler=handler, record=record)
                setattr(record, FORWARDED_MARK, True)
        finally:
            self.release()

    @override
    def close(self) -> None:
        """Give what is still held the stdlib's last-resort handling: every held record reaches stderr.

        Every one of them, and not only a warning or worse. The last resort's own level is meant for a
        record emitted before anything was configured, where nobody has said what is worth seeing; these
        records passed the root logger's level, which ``configure`` set from the configuration, so each one
        is a line this process was asked to show. The only moment this runs with anything still held is a
        boot that died before its sink arrived, which is exactly when the trail a verbose run was turned on
        to produce is the thing being looked for. Each one passes the last-resort filter first, so a secret
        a held line quoted is scrubbed on this path as it would have been by the sink, and a record the
        filter rejects, one the redaction could neither scrub nor strip, is not written.
        """
        self.acquire()
        try:
            held, self._held = self._held, []
        finally:
            self.release()
        last_resort = logging.lastResort
        if last_resort is not None:
            for record in held:
                if self._last_resort_filter is not None and not self._last_resort_filter.filter(record):
                    continue
                last_resort.handle(record)
        super().close()
