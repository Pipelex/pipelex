"""Per-instance on-disk clone cache for fetched method packages, keyed by resolved commit SHA.

A `method_ref` run fetches a public git repository. Cloning on every request would hammer
GitHub's anonymous-clone rate limits and add seconds of latency, so this server keeps the
clones on local disk — but **never keyed by tag**: tags can move, and a moved tag must
change what runs. Instead, each request first resolves the reference to its commit SHA with
a cheap `git ls-remote` (no clone), then looks the clone up by that SHA. A repointed tag or
an advanced default branch resolves to a new SHA and therefore a fresh clone; the cached
copy of the old SHA ages out on its own.

The cache is per server instance (a directory under the system temp dir by default,
`METHOD_CACHE_DIR` to override) and bounded three ways — clone count, total bytes, and age —
via the `MAX_METHOD_CACHE_*` knobs in `api.limits`. Eviction runs on insert, oldest-first by
last use, and never evicts the most recently used entry. Package location, bounds, and the
structures scan are NOT cached: they re-run against the cached clone on every request, so a
deployment-mode change (or a ceiling change) applies immediately.

Concurrency: clones land in a per-request staging directory and are installed with an atomic
`rename`, so two concurrent requests for the same SHA cannot corrupt each other — the loser
of the rename race discards its staging copy and uses the winner's. The resolution seam
(`api.method_source`) copies everything it needs out of the cached clone before the run
starts, so eviction can never pull a directory out from under a running pipeline.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from functools import cache
from pathlib import Path

from pipelex import log
from pipelex.methods.exceptions import MethodFetchError
from pipelex.methods.fetching import FetchedMethodPackage, ensure_package_within_bounds, fetch_method_package
from pipelex.methods.method_ref import MethodRef
from pipelex.methods.package_locator import locate_package_in_clone
from pipelex.system.environment import get_optional_env

from api.limits import MAX_METHOD_CACHE_AGE_SECONDS, MAX_METHOD_CACHE_CLONES, MAX_METHOD_CACHE_TOTAL_BYTES

LS_REMOTE_TIMEOUT_SECONDS = 60

_STAGING_DIR_NAME = ".staging"
_DEFAULT_CACHE_DIR_NAME = "pipelex-api-method-cache"


def _run_ls_remote(*, clone_url: str, ref_patterns: list[str], ref_str: str) -> list[tuple[str, str]]:
    """Run `git ls-remote` for the given ref patterns and return `(sha, ref_name)` pairs.

    Raises:
        MethodFetchError: If git is unavailable, the remote cannot be reached, or the call times out.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv, no shell; the URL is derived from the validated address grammar
            ["git", "ls-remote", clone_url, *ref_patterns],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=LS_REMOTE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise MethodFetchError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to fetch method '{ref_str}': could not reach the repository ({exc.stderr.strip()})"
        raise MethodFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out resolving method '{ref_str}' against the remote repository"
        raise MethodFetchError(msg) from exc

    pairs: list[tuple[str, str]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def resolve_remote_commit_sha(*, ref: MethodRef, clone_url: str | None = None) -> str:
    """Resolve a method reference to the commit SHA it currently points at, without cloning.

    For a `@<tag>` reference, only `refs/tags/<tag>` is consulted — a branch of the same
    name does not count, so `@main` is refused here, before any clone (the same tags-only
    rule `pipelex.methods.fetching.ensure_cloned_at_tag` enforces after a clone). For an
    annotated tag the peeled (`^{}`) commit SHA is returned, matching what `rev-parse HEAD`
    reports inside a clone at that tag. A bare reference resolves the default branch `HEAD`.

    Args:
        ref: The parsed method reference.
        clone_url: Override for the derived clone URL (tests, non-default remotes).

    Returns:
        The full commit SHA the reference resolves to right now.

    Raises:
        MethodFetchError: If the remote cannot be reached, or `@<tag>` does not name a tag.
    """
    effective_clone_url = clone_url or ref.clone_url
    if ref.tag:
        pairs = _run_ls_remote(
            clone_url=effective_clone_url,
            ref_patterns=[f"refs/tags/{ref.tag}", f"refs/tags/{ref.tag}^{{}}"],
            ref_str=ref.ref_str,
        )
        peeled = [sha for sha, name in pairs if name.endswith("^{}")]
        if peeled:
            return peeled[0]
        direct = [sha for sha, name in pairs if name == f"refs/tags/{ref.tag}"]
        if direct:
            return direct[0]
        msg = (
            f"'{ref.tag}' in method reference '{ref.ref_str}' does not name a git tag on the repository — "
            f"`@<tag>` pins a git tag (recommended form vX.Y.Z); branch names are not accepted."
        )
        raise MethodFetchError(msg)
    pairs = _run_ls_remote(clone_url=effective_clone_url, ref_patterns=["HEAD"], ref_str=ref.ref_str)
    head = [sha for sha, name in pairs if name == "HEAD"]
    if not head:
        msg = f"The repository behind method reference '{ref.ref_str}' has no HEAD (empty repository?)"
        raise MethodFetchError(msg)
    return head[0]


def _directory_size_bytes(directory: Path) -> int:
    total = 0
    for file_path in directory.rglob("*"):
        if file_path.is_file() and not file_path.is_symlink():
            total += file_path.stat().st_size
    return total


class MethodCloneCache:
    """SHA-keyed, bounded, on-disk cache of method-package clones (see the module docstring)."""

    def __init__(self, *, root_dir: Path) -> None:
        self._root = root_dir
        self._lock = threading.Lock()

    def get_or_fetch(self, *, ref: MethodRef, clone_url: str | None = None) -> FetchedMethodPackage:
        """Return the package a reference points at, cloning only when its SHA is not cached.

        Always re-runs package location and the bounds check against the (possibly cached)
        clone — only the clone itself is cached, never a verdict about it.

        Args:
            ref: The parsed method reference.
            clone_url: Override for the derived clone URL (tests, non-default remotes).

        Returns:
            The fetched package, rooted inside the cache directory.

        Raises:
            MethodFetchError: If SHA resolution or the clone fails, or `@<tag>` is not a tag.
            MethodPackageNotFoundError: If no package matches the requested address.
            MethodPackageAmbiguityError: If more than one package matches.
            MethodPackageTooLargeError: If the selected package exceeds the ceilings.
        """
        commit_sha = resolve_remote_commit_sha(ref=ref, clone_url=clone_url)
        clone_dir = self._root / commit_sha
        with self._lock:
            if clone_dir.is_dir():
                os.utime(clone_dir)  # LRU bookkeeping: mtime is the eviction order
                return self._package_from_clone(ref=ref, clone_dir=clone_dir, commit_sha=commit_sha)

        # Miss: clone into a per-request staging dir (outside the lock — clones are slow),
        # then install atomically. A tag repointed between ls-remote and clone resolves to the
        # clone's ACTUAL commit SHA — that is what gets recorded and keyed, never the stale one.
        staging_root = self._root / _STAGING_DIR_NAME
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root / uuid.uuid4().hex
        try:
            fetched = fetch_method_package(ref=ref, dest_dir=staging_dir, clone_url=clone_url)
            target_dir = self._root / fetched.commit_sha
            with self._lock:
                if not target_dir.exists():
                    try:
                        staging_dir.rename(target_dir)
                    except OSError:
                        # A concurrent request installed the same SHA between the check and the
                        # rename; its copy is identical (same commit), so use it.
                        log.debug(f"Method clone cache: lost the install race for {fetched.commit_sha}, reusing the winner's copy")
                self._evict()
                return self._package_from_clone(ref=ref, clone_dir=target_dir, commit_sha=fetched.commit_sha)
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _package_from_clone(self, *, ref: MethodRef, clone_dir: Path, commit_sha: str) -> FetchedMethodPackage:
        """Locate + bound the requested package inside a cached clone (never cached themselves)."""
        located = locate_package_in_clone(clone_root=clone_dir, requested_address=ref.address)
        ensure_package_within_bounds(package_dir=located.package_dir, package_address=located.full_address)
        return FetchedMethodPackage(
            ref=ref,
            full_address=located.full_address,
            commit_sha=commit_sha,
            clone_dir=clone_dir,
            package_dir=located.package_dir,
            manifest=located.manifest,
        )

    def _evict(self) -> None:
        """Enforce the age, count, and byte bounds — oldest-first, keeping the newest entry.

        Called with the lock held, right after an install. Best-effort by design: a clone
        directory another process already removed is simply skipped.
        """
        entries = sorted(
            (entry for entry in self._root.iterdir() if entry.is_dir() and entry.name != _STAGING_DIR_NAME),
            key=lambda entry: entry.stat().st_mtime,
        )
        if not entries:
            return
        newest = entries[-1]
        now = time.time()
        survivors: list[Path] = []
        for entry in entries:
            if entry != newest and now - entry.stat().st_mtime > MAX_METHOD_CACHE_AGE_SECONDS:
                shutil.rmtree(entry, ignore_errors=True)
            else:
                survivors.append(entry)
        total_bytes = sum(_directory_size_bytes(entry) for entry in survivors)
        while len(survivors) > 1 and (len(survivors) > MAX_METHOD_CACHE_CLONES or total_bytes > MAX_METHOD_CACHE_TOTAL_BYTES):
            oldest = survivors.pop(0)
            total_bytes -= _directory_size_bytes(oldest)
            shutil.rmtree(oldest, ignore_errors=True)


@cache
def get_method_clone_cache() -> MethodCloneCache:
    """The per-instance clone cache singleton.

    The root directory is `METHOD_CACHE_DIR` when set, else a fixed directory under the
    system temp dir — per instance, surviving requests but not the host, which is exactly
    the cache's contract (a cold instance re-clones once per SHA).
    """
    configured = get_optional_env("METHOD_CACHE_DIR")
    root_dir = Path(configured) if configured else Path(tempfile.gettempdir()) / _DEFAULT_CACHE_DIR_NAME
    root_dir.mkdir(parents=True, exist_ok=True)
    return MethodCloneCache(root_dir=root_dir)
