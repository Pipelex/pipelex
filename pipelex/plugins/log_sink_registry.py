from typing import Protocol

from pipelex.plugins.exceptions import UnknownLogSinkError
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class LogSinkFactoryFn(Protocol):
    """A plugin's factory for one log sink: whole log config and the boot's secrets provider in, sink out.

    The whole config (not a pre-resolved sub-config) is passed so a factory can read whatever it needs —
    the stream target, its own settings section — at the boot apply-point, never at registration. The
    sink's handler is built later still, when boot installs it, which is where a missing dependency
    fails loud.

    The secrets provider is passed rather than read off the hub, because boot builds it before the sink
    but sets it on the hub only afterwards: the keyword is the one way a factory reaches a secret, so
    the order is one the type checker enforces rather than a ``RuntimeError`` at boot. A sink whose
    settings name no secret accepts it and ignores it. ``config`` is positional-only here so that an
    implementation may spell its own first parameter as it likes.
    """

    def __call__(self, config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink: ...


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
