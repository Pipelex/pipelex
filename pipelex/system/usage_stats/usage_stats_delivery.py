"""The start of the detached sender a CLI command leaves behind to drain pipelex's spool after it exits.

The sender is `usage_stats_core` itself, started by its file path in isolated mode, so it imports the standard library
alone and never the `pipelex` package: it delivers from any interpreter that can run this file, whether or not that
interpreter sees pipelex, and it starts in a fraction of the time a pipelex import takes. The contract is
`conformance/specs/usage-statistics.md`, "Senders".
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import] — starts the detached sender, a fixed file of this package
import sys
from pathlib import Path

from pipelex.system.usage_stats import usage_stats_core
from pipelex.system.usage_stats.usage_stats_contract import TOOL_NAME
from pipelex.system.usage_stats.usage_stats_core import UsageStatsState, sender_command


def start_detached_sender(*, state: UsageStatsState, origin: str) -> bool:
    """Start the process that drains pipelex's spool after the command exits: no terminal, no output, outliving it.

    Returns:
        Whether the process started; when it did not, the command posts in-process instead.
    """
    if not sys.executable or not Path(usage_stats_core.__file__).is_file():
        return False
    command = sender_command(executable=sys.executable, home=state.home, origin=origin, tool=TOOL_NAME)
    try:
        if sys.platform == "win32":
            creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                cwd=state.state_dir,
                creationflags=creation_flags,
            )
        else:
            subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true] — a fixed argument list, no shell
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                cwd=state.state_dir,
                start_new_session=True,
            )
    except (OSError, ValueError):
        return False
    return True
