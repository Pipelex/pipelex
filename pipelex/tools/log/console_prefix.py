"""What the console puts before a record's message: its logger's top-level package name, on the lines the setting chooses.

Nearly every line on a Pipelex console is Pipelex's own, so by default a prefix naming Pipelex says nothing and costs
columns: the ``package_prefix`` setting's ``libraries`` value leaves a Pipelex line bare and starts a line from another
library, an HTTP client's or a provider SDK's, with its logger's top-level package name, which the sink prints dimmed,
so the reader still sees which library spoke. ``all`` names the package on every line, where it tells the runtime, the
API server and a plugin apart, and ``none`` names it on none. The root logger's lines carry no prefix under any value.
"""

from pipelex.tools.log.log_config import PackagePrefix

#: The logger of a record logged on the root logger, which names no library.
ROOT_LOGGER_NAME = "root"

#: The top-level package of the runtime's own loggers.
PIPELEX_PACKAGE = "pipelex"

#: What starts the top-level package of a Pipelex distribution beside the runtime, ``pipelex_api`` or a plugin's named that
#: way. A plugin whose package is named otherwise counts as another library.
PIPELEX_PACKAGE_PREFIX = f"{PIPELEX_PACKAGE}_"


def prefixed_package_name(*, logger_name: str, package_prefix: PackagePrefix) -> str | None:
    """The top-level package of the logger, which the console prints before the message, or ``None`` for no prefix.

    Under ``libraries``, a logger under ``pipelex`` or a ``pipelex_`` package, the runtime's, the API server's or a
    plugin's named that way, has none. The root logger has none under any value.
    """
    if logger_name == ROOT_LOGGER_NAME:
        return None
    package = logger_name.split(".", 1)[0]
    match package_prefix:
        case PackagePrefix.LIBRARIES:
            if package == PIPELEX_PACKAGE or package.startswith(PIPELEX_PACKAGE_PREFIX):
                return None
            return package
        case PackagePrefix.ALL:
            return package
        case PackagePrefix.NONE:
            return None
