"""How queued events leave the machine: the checks before each post, the spool drain, and the detached sender's start.

Before each post a sender runs the legacy migration, sends nothing when `disabled` exists, and drops every event whose
`distinct_id` is not the current identifier, since those were made under an identifier `reset-id` has since replaced.
A sender makes one attempt per file per run, within its budget; the next command's sender retries what is left. The
contract is `conformance/specs/usage-statistics.md`, "Delivery".

Standard library only, for the reason `usage_stats_contract` gives.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import] — starts the detached sender, a fixed module of this package
import sys
import time
from pathlib import Path
from typing import Any

from pipelex.system.usage_stats.usage_stats_spool import claim, pending_files, prune, read_spool_events, release, rewrite_spool_file
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState
from pipelex.system.usage_stats.usage_stats_transport import PostVerdict, post_batch

#: The module the detached sender runs, as `python -I -m <module>`.
SENDER_MODULE = "pipelex.system.usage_stats.usage_stats_sender"


def screen_events(*, state: UsageStatsState, events: list[dict[str, Any]], own_id: str | None) -> list[dict[str, Any]] | None:
    """The events still to send, checked immediately before a post; `None` when statistics were turned off since.

    Args:
        state: The shared state.
        events: The events about to be posted.
        own_id: The identifier this process sends under when `id` holds none it can read: a process-local identifier,
            whose events are this process's own and still to be sent. A detached sender has none.
    """
    state.migrate_legacy_opt_out()
    if state.is_disabled():
        return None
    current_id = state.read_installation_id() or own_id
    return [event for event in events if event.get("distinct_id") == current_id]


def send_claimed_file(*, state: UsageStatsState, claimed: Path, origin: str, deadline: float, own_id: str | None) -> PostVerdict | None:
    """Post a file this sender claimed, then delete it or give it back by PostHog's answer; `None` when nothing was posted."""
    events = read_spool_events(path=claimed)
    if events is None:
        claimed.unlink(missing_ok=True)
        return None
    kept = screen_events(state=state, events=events, own_id=own_id)
    if not kept:
        claimed.unlink(missing_ok=True)
        return None
    if len(kept) != len(events):
        try:
            rewrite_spool_file(path=claimed, events=kept)
        except OSError:
            # The dropped events must never be sent: a file that cannot be rewritten without them is deleted with them.
            claimed.unlink(missing_ok=True)
            return None
    verdict = post_batch(origin=origin, events=kept, timeout_seconds=deadline - time.monotonic())
    if verdict.is_final:
        claimed.unlink(missing_ok=True)
    else:
        release(claimed=claimed)
    return verdict


def drain_spool(*, state: UsageStatsState, tool: str, origin: str, budget_ms: int, only: Path | None = None, own_id: str | None = None) -> None:
    """Post the files of `tool`'s spool, oldest first, within `budget_ms`; with `only`, that one file alone."""
    deadline = time.monotonic() + budget_ms / 1000
    spool_dir = state.spool_dir(tool=tool)
    candidates: list[Path]
    if only is None:
        prune(spool_dir=spool_dir)
        candidates = pending_files(spool_dir=spool_dir)
    else:
        candidates = [only]
    for candidate in candidates:
        if time.monotonic() >= deadline:
            return
        claimed = claim(path=candidate)
        if claimed is None:
            continue
        send_claimed_file(state=state, claimed=claimed, origin=origin, deadline=deadline, own_id=own_id)


def post_in_process(
    *, state: UsageStatsState, events: list[dict[str, Any]], origin: str, deadline: float, own_id: str | None
) -> tuple[PostVerdict | None, list[dict[str, Any]]]:
    """Post events held in memory after the checks; the verdict (`None` when nothing was posted) and the events posted."""
    kept = screen_events(state=state, events=events, own_id=own_id)
    if not kept:
        return None, []
    return post_batch(origin=origin, events=kept, timeout_seconds=deadline - time.monotonic()), kept


def start_detached_sender(*, state: UsageStatsState, origin: str) -> bool:
    """Start the process that drains pipelex's spool after the command exits: no terminal, no output, outliving it.

    Returns:
        Whether the process started; when it did not, the command posts in-process instead.
    """
    if not sys.executable:
        return False
    command = [sys.executable, "-I", "-m", SENDER_MODULE, "--home", str(state.home), "--origin", origin]
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
