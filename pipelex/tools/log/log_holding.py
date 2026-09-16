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
        # arrives either before the drain and is held, or after it and goes straight to the handler
        # that took the held ones: never into a list nobody reads again. A thread that picked this
        # handler off the root logger just before it was removed is the one this is for.
        if self._released_to is not None:
            self._released_to.handle(record)
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
                try:
                    handler.handle(record)
                except Exception:  # ruff: ignore[blind-except]
                    handler.handleError(record)
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
