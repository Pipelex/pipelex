from collections.abc import Callable

from pipelex.plugins.exceptions import UnknownLogSinkError
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink

# A plugin's factory for one log sink: whole log config in, sink out. The whole config (not a
# pre-resolved sub-config) is passed so a factory can read whatever it needs — the stream target, its
# own settings section — at the boot apply-point, never at registration. The sink's handler is built
# later still, when boot installs it, which is where a missing dependency fails loud.
LogSinkFactoryFn = Callable[[LogConfig], LogSink]


class LogSinkRegistry:
    """Read view over the log-sink factories contributed by discovered plugins.

    Keyed by the open sink ``method`` token (a ``str``; the built-in ``LogSinkPlugin`` registers the
    ``LogSinkMethod`` values, an external plugin registers e.g. ``"syslog"``). Built once at boot from the
    registrar's accumulated ``log_sinks``; boot reads ``runtime.log.sink`` and calls the looked-up
    factory to produce the one sink installed on the root logger. Mirrors ``StorageProviderRegistry``.
    """

    def __init__(self, log_sinks: dict[str, LogSinkFactoryFn]):
        self._log_sinks: dict[str, LogSinkFactoryFn] = dict(log_sinks)

    def get_required(self, *, method: str) -> LogSinkFactoryFn:
        factory = self._log_sinks.get(method)
        if factory is None:
            raise UnknownLogSinkError(method=method, registered_methods=self.methods)
        return factory

    def has(self, *, method: str) -> bool:
        return method in self._log_sinks

    @property
    def methods(self) -> list[str]:
        return list(self._log_sinks)
