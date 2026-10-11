"""The detached sender a CLI command starts as `python -I -m pipelex.system.usage_stats.usage_stats_sender`.

It posts every file of pipelex's spool, the one its command just wrote among them, within a budget of ten seconds, and
exits. It runs with no terminal and no output, outliving the command that started it, and imports nothing of pipelex
but this package's standard-library modules, which keep it small.
"""

import argparse
import sys
from pathlib import Path

from pipelex.system.usage_stats.usage_stats_contract import BUDGET_DETACHED_SENDER_MS, CAPTURE_HOST, TOOL_NAME
from pipelex.system.usage_stats.usage_stats_delivery import drain_spool
from pipelex.system.usage_stats.usage_stats_environment import is_loopback_origin
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState


def main(*, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipelex-usage-stats-sender", add_help=False)
    parser.add_argument("--home", required=True)
    parser.add_argument("--origin", required=True)
    arguments = parser.parse_args(argv)
    origin: str = arguments.origin
    # The origin was checked by the command that started this process; it is checked again here, so this module can
    # never be made to post anywhere but the project or the machine itself.
    if origin != CAPTURE_HOST and not is_loopback_origin(origin=origin):
        return 2
    state = UsageStatsState(home=Path(arguments.home))
    drain_spool(state=state, tool=TOOL_NAME, origin=origin, budget_ms=BUDGET_DETACHED_SENDER_MS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
