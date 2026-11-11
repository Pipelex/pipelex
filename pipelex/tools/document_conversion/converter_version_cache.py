"""A converter's version, asked once however many conversions start at the same time.

The `soffice` backend's: a backend lives for the process and is first used by whichever steps convert at once, each
needing the version to stamp its PDF, and without a lock every one of them would start a `soffice --version` process.
Gotenberg needs none, since each of its answers names the version of the process that made the PDF.

The lock is one per event loop, since a backend outlives the loop it was first used on, as an activity may run each
step on another, and an `asyncio.Lock` waited on is bound to its loop.
"""

import asyncio
import weakref
from collections.abc import Awaitable, Callable


class ConverterVersionCache:
    """The version of one converter, fetched by the first caller while the others wait, then kept."""

    def __init__(self) -> None:
        """Start with no version: the first caller fetches it."""
        self._version: str | None = None
        self._lock_by_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = weakref.WeakKeyDictionary()

    async def get_or_fetch(self, *, fetch: Callable[[], Awaitable[str]]) -> str:
        """The kept version, or the one `fetch` answers, fetched once by the first of the callers waiting for it.

        A fetch that fails keeps nothing, so the next caller fetches again.
        """
        if self._version is not None:
            return self._version
        async with self._lock_of_running_loop():
            if self._version is None:
                self._version = await fetch()
            return self._version

    def _lock_of_running_loop(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._lock_by_loop.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            self._lock_by_loop[loop] = lock
        return lock
