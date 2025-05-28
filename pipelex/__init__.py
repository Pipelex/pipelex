from pipelex.tools.log.log import log
from pipelex.tools.misc.pretty import pretty_print

__all__ = [
    "log",
    "pretty_print",
]

# ------------------------------------------------------------
# Keep <project>/pipelex_libraries on sys.path for every installer (Fix for uv)
# ------------------------------------------------------------

from ._bootstrap_user_libs import activate as _px_bootstrap_user_libs

_px_bootstrap_user_libs()
