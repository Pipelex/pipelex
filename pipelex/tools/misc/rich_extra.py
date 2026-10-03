"""Rich is the ``cli`` extra: this module names the extra and says so when it is missing.

Nothing here imports Rich at module level, and nothing here imports ``pipelex`` at module level either:
the pretty-print engine imports this module, and the engine sits under the log package every
``import pipelex`` loads first.
"""

import importlib
import importlib.util

# The extra that installs Rich: the console log sink, the pretty-print engine's ``rich`` mode, the
# ``rendered_pretty`` renderings and the CLI all render through it.
RICH_EXTRA_NAME = "cli"

#: What a listing whose result is a Rich table says when the extra is missing. The model listings and the pipe
#: listing share it: each builds a table and has nothing else to print it as.
RICH_TABLE_MISSING_MESSAGE = "This listing prints its result in a Rich table."


def require_rich(*, message: str) -> None:
    """Import Rich, or raise ``MissingDependencyError`` naming the ``cli`` extra.

    Called before a lazy ``from rich… import …``, so a process without the extra is told what to
    install, and what to select instead, rather than handed a bare ``ModuleNotFoundError``.

    Args:
        message: What renders through Rich here, and the Rich-free alternative when there is one.

    Raises:
        MissingDependencyError: If Rich cannot be imported.
    """
    try:
        importlib.import_module("rich")
    except ImportError as exc:
        # Deferred: see the module docstring.
        from pipelex.system.exceptions import MissingDependencyError  # ruff: ignore[import-outside-top-level]

        raise MissingDependencyError(dependency_name="rich", extra_name=RICH_EXTRA_NAME, message=message) from exc


def is_rich_installed() -> bool:
    """Whether Rich is installed, asked without importing it, for a rendering that has a Rich-free fallback rather than a failure."""
    try:
        return importlib.util.find_spec("rich") is not None
    except (ImportError, ValueError):
        # An import hook refusing the name answers as an absent package would; a ``rich`` module left in
        # ``sys.modules`` without a spec is not an installation either.
        return False
