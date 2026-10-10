"""What the console puts before a record's message: nothing on a Pipelex line, the package name of any other library.

Nearly every line on a Pipelex console is Pipelex's own, so a prefix naming Pipelex says nothing and costs columns. A
line from another library, an HTTP client's or a provider SDK's, starts with its logger's top-level package name, which
the sink prints dimmed, so the reader still sees which library spoke. The root logger's lines carry no prefix either.
"""

#: The logger of a record logged on the root logger, which names no library.
ROOT_LOGGER_NAME = "root"

#: The top-level package of the runtime's own loggers.
PIPELEX_PACKAGE = "pipelex"

#: What starts the top-level package of a Pipelex distribution beside the runtime, ``pipelex_api`` or a plugin's named that
#: way. A plugin whose package is named otherwise gets its prefix like any other library.
PIPELEX_PACKAGE_PREFIX = f"{PIPELEX_PACKAGE}_"


def foreign_package_name(*, logger_name: str) -> str | None:
    """The top-level package of a logger that is not Pipelex's, which the console prints before the message; else ``None``.

    A logger under ``pipelex`` or a ``pipelex_`` package, the runtime's, the API server's or a plugin's named that way,
    and the root logger have none.
    """
    if logger_name == ROOT_LOGGER_NAME:
        return None
    package = logger_name.split(".", 1)[0]
    if package == PIPELEX_PACKAGE or package.startswith(PIPELEX_PACKAGE_PREFIX):
        return None
    return package
