"""The only git-touching module of the drift engine: index reads via git plumbing.

Digest sourcing is index-based (staged blob OIDs from `git ls-files -s`), so matching
and hashing share one source, content is filter-normalized (CRLF/smudge safe), and the
digest covers exactly what would land in the commit. Working-tree bytes are never hashed.
"""

from __future__ import annotations

import subprocess  # ruff: ignore[suspicious-subprocess-import]
from pathlib import Path

from pipelex.cli.dev_cli.commands.drift.exceptions import DriftGitError

GIT_TIMEOUT_SECONDS = 30
OID_PREFIX = "blob:"


def _run_git(args: list[str], *, cwd: Path) -> str:
    """Run one git plumbing command and return stdout; every failure is a DriftGitError."""
    try:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["git", *args],  # ruff: ignore[start-process-with-partial-path]
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        msg = "git binary not found on PATH — the drift commands need git"
        raise DriftGitError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s"
        raise DriftGitError(msg) from exc
    if result.returncode != 0:
        msg = f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        raise DriftGitError(msg)
    return result.stdout


def get_repo_toplevel(*, cwd: Path | None = None) -> Path:
    """Resolve the git toplevel directory from cwd (where drift.toml and .drift/ live)."""
    output = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd or Path.cwd())
    return Path(output.strip())


def read_staged_files(repo_root: Path) -> dict[str, str]:
    """Read the whole index in one `git ls-files -s -z` call: path → "blob:<oid>".

    The keys are the tracked-file set the matcher runs over and the values are the
    staged blob OIDs the digest hashes — one call, one source.

    Raises:
        DriftGitError: On any git failure, malformed output, or unmerged index entries.
    """
    output = _run_git(["ls-files", "-s", "-z"], cwd=repo_root)
    staged: dict[str, str] = {}
    for entry in output.split("\0"):
        if not entry:
            continue
        header, separator, path = entry.partition("\t")
        header_parts = header.split()
        if not separator or len(header_parts) != 3:
            msg = f"Malformed `git ls-files -s` entry: {entry!r}"
            raise DriftGitError(msg)
        _mode, oid, stage = header_parts
        if stage != "0":
            msg = f"Unmerged index entry for '{path}' — resolve the merge, then re-run"
            raise DriftGitError(msg)
        staged[path] = OID_PREFIX + oid
    return staged


def read_unstaged_modified(repo_root: Path) -> list[str]:
    """Tracked files whose working-tree content differs from the index (for ack-time warnings)."""
    output = _run_git(["diff", "--name-only", "-z"], cwd=repo_root)
    return sorted(path for path in output.split("\0") if path)


def read_untracked(repo_root: Path) -> list[str]:
    """Untracked, non-ignored files (for ack-time warnings — they are invisible to the index)."""
    output = _run_git(["ls-files", "--others", "--exclude-standard", "-z"], cwd=repo_root)
    return sorted(path for path in output.split("\0") if path)


def stage_file(path: Path, *, repo_root: Path) -> None:
    """Stage one file into the index (`drift ack` auto-stages the ack file it writes)."""
    _run_git(["add", "--", str(path)], cwd=repo_root)


def get_git_user_name(repo_root: Path) -> str | None:
    """The configured git user.name, or None when unset (callers must then require --by)."""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],  # ruff: ignore[start-process-with-partial-path]
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
