from pipelex._bootstrap_user_libs import activate as _px_bootstrap_user_libs
from pipelex.tools.log.log import log
from pipelex.tools.misc.pretty import pretty_print, pretty_print_md

__all__ = [
    "log",
    "pretty_print",
    "pretty_print_md",
]

# ------------------------------------------------------------
# Keep <project>/pipelex_libraries on sys.path for every installer (Fix for uv)
# ------------------------------------------------------------

_px_bootstrap_user_libs()
