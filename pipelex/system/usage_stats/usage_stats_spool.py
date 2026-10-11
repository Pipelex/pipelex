"""A tool's queue of unsent events, `spool/<tool>/` in the shared state.

A file is named `<created-ms>-<random>.json` and holds `{"spool_version": 1, "events": [...]}`. It is written under a
name starting with a dot and renamed into place, so a reader never sees it partial, and readers ignore names starting
with a dot. A sender claims a file by renaming it to `<name>.sending-<random>`, so two senders never post one file, and
after its attempt deletes it or renames it back. The contract is `conformance/specs/usage-statistics.md`, "The spool".

Standard library only, for the reason `usage_stats_contract` gives.
"""

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, cast

from pipelex.system.usage_stats.usage_stats_contract import (
    SPOOL_MAX_AGE_DAYS,
    SPOOL_MAX_FILES_PER_TOOL,
    SPOOL_STALE_CLAIM_MINUTES,
    SPOOL_STALE_TEMP_MINUTES,
    SPOOL_VERSION,
)

SPOOL_FILE_SUFFIX = ".json"
CLAIM_MARKER = ".sending-"
_TEMP_PREFIX = ".tmp-"


def _created_ms(*, path: Path) -> int | None:
    """The creation time a spool file's name starts with, or `None` for a name that is not a spool file's."""
    prefix = path.name.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def is_pending(*, path: Path) -> bool:
    """Whether `path` is a spool file waiting for a sender: not temporary, not claimed."""
    name = path.name
    return not name.startswith(".") and CLAIM_MARKER not in name and name.endswith(SPOOL_FILE_SUFFIX) and _created_ms(path=path) is not None


def pending_files(*, spool_dir: Path) -> list[Path]:
    """The files waiting in `spool_dir`, oldest first."""
    try:
        entries = [entry for entry in spool_dir.iterdir() if is_pending(path=entry)]
    except OSError:
        return []
    return sorted(entries, key=lambda entry: (_created_ms(path=entry) or 0, entry.name))


def write_spool_file(*, spool_dir: Path, events: list[dict[str, Any]]) -> Path:
    """Queue `events` in a new file, then keep at most the contract's number of files, deleting the oldest.

    Raises:
        OSError: when the file could not be written.
    """
    spool_dir.mkdir(parents=True, exist_ok=True)
    final_path = spool_dir / f"{int(time.time() * 1000)}-{secrets.token_hex(6)}{SPOOL_FILE_SUFFIX}"
    temporary = spool_dir / f"{_TEMP_PREFIX}{secrets.token_hex(6)}"
    try:
        temporary.write_text(json.dumps({"spool_version": SPOOL_VERSION, "events": events}), encoding="utf-8")
        temporary.rename(final_path)
    finally:
        temporary.unlink(missing_ok=True)
    _enforce_file_limit(spool_dir=spool_dir)
    return final_path


def _enforce_file_limit(*, spool_dir: Path) -> None:
    waiting = pending_files(spool_dir=spool_dir)
    for oldest in waiting[: max(0, len(waiting) - SPOOL_MAX_FILES_PER_TOOL)]:
        oldest.unlink(missing_ok=True)


def read_spool_events(*, path: Path) -> list[dict[str, Any]] | None:
    """The events a spool file holds, or `None` for a file that is not one: unreadable, not JSON, or of another shape."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload_dict = cast("dict[str, Any]", payload)
    events: object = payload_dict.get("events")
    if payload_dict.get("spool_version") != SPOOL_VERSION or not isinstance(events, list):
        return None
    event_list = cast("list[object]", events)
    if not all(isinstance(event, dict) for event in event_list):
        return None
    return cast("list[dict[str, Any]]", event_list)


def rewrite_spool_file(*, path: Path, events: list[dict[str, Any]]) -> None:
    """Replace the events of a file this sender has claimed, as a whole.

    Raises:
        OSError: when the file could not be replaced.
    """
    temporary = path.parent / f"{_TEMP_PREFIX}{secrets.token_hex(6)}"
    try:
        temporary.write_text(json.dumps({"spool_version": SPOOL_VERSION, "events": events}), encoding="utf-8")
        Path(temporary).replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def claim(*, path: Path) -> Path | None:
    """Claim a waiting file for this sender, or `None` when another sender took it first.

    The claim's modification time is set to now, so a claim's age is how long its sender has held it.
    """
    claimed = path.with_name(f"{path.name}{CLAIM_MARKER}{secrets.token_hex(6)}")
    try:
        path.rename(claimed)
    except OSError:
        return None
    try:
        os.utime(claimed)
    except OSError:
        # The claim stands without its fresh time: it can only look stale sooner, and be resent, never be lost.
        return claimed
    return claimed


def release(*, claimed: Path) -> None:
    """Give a claimed file back for the next sender, under its name before the claim."""
    original = claimed.with_name(claimed.name.split(CLAIM_MARKER, 1)[0])
    try:
        claimed.rename(original)
    except OSError:
        return


def prune(*, spool_dir: Path) -> None:
    """Tidy a spool before draining it: give back stale claims, delete stale temporary files and files past their age."""
    now = time.time()
    try:
        entries = list(spool_dir.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            age_seconds = now - entry.stat().st_mtime
        except OSError:
            continue
        name = entry.name
        if name.startswith("."):
            if age_seconds > SPOOL_STALE_TEMP_MINUTES * 60:
                entry.unlink(missing_ok=True)
        elif CLAIM_MARKER in name:
            if age_seconds > SPOOL_STALE_CLAIM_MINUTES * 60:
                release(claimed=entry)
        elif is_pending(path=entry):
            created_ms = _created_ms(path=entry) or 0
            if now * 1000 - created_ms > SPOOL_MAX_AGE_DAYS * 24 * 3600 * 1000:
                entry.unlink(missing_ok=True)
