"""Unit tests for the SHA-keyed method clone cache, against real local git repositories.

Everything runs on-disk (`file://` remotes) — no network. Pins the cache's contract: the
reference is resolved to its commit SHA by `ls-remote` before any clone (tags-only for
`@<tag>`), a cached SHA is never re-cloned, a moved tag resolves to a new SHA and a fresh
clone (never cache by tag alone), and the bounds evict oldest-first while keeping the newest
entry.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest
from pipelex.methods.exceptions import MethodFetchError
from pipelex.methods.fetching import fetch_method_package
from pipelex.methods.method_ref import parse_method_ref
from pytest_mock import MockerFixture

from api.method_cache import MethodCloneCache, resolve_remote_commit_sha
from tests.unit._constants import STUB_METHOD_MANIFEST, VALID_MTHDS

_REF = parse_method_ref("github.com/pipelex/methods/documents@v0.1.0")
_BARE_REF = parse_method_ref("github.com/pipelex/methods/documents")


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(  # noqa: S603 — fixed argv against the test's own tmp repo
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "-c", "commit.gpgsign=false", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> tuple[str, Path]:
    """A local origin repository holding the stub package, tagged `v0.1.0`; returns (clone_url, repo_dir)."""
    repo = tmp_path / "origin"
    package_dir = repo / "methods" / "documents"
    package_dir.mkdir(parents=True)
    (package_dir / "METHODS.toml").write_text(STUB_METHOD_MANIFEST, encoding="utf-8")
    (package_dir / "documents.mthds").write_text(VALID_MTHDS, encoding="utf-8")
    _git("init", "-b", "main", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", "seed package", cwd=repo)
    _git("tag", "-a", "v0.1.0", "-m", "first tag", cwd=repo)
    return f"file://{repo}", repo


class TestMethodCloneCache:
    def test_resolve_remote_commit_sha_for_tag_and_head(self, origin: tuple[str, Path]):
        clone_url, repo = origin
        head_sha = _git("rev-parse", "HEAD", cwd=repo)
        # An annotated tag resolves to its PEELED commit SHA — the same value `rev-parse HEAD`
        # reports inside a clone at that tag — not the tag object's own SHA.
        assert resolve_remote_commit_sha(ref=_REF, clone_url=clone_url) == head_sha
        # A bare reference resolves the default branch HEAD.
        assert resolve_remote_commit_sha(ref=_BARE_REF, clone_url=clone_url) == head_sha

    def test_branch_names_are_refused_as_tags(self, origin: tuple[str, Path]):
        clone_url, _ = origin
        branch_ref = parse_method_ref("github.com/pipelex/methods/documents@main")
        with pytest.raises(MethodFetchError, match="does not name a git tag"):
            resolve_remote_commit_sha(ref=branch_ref, clone_url=clone_url)

    def test_a_cached_sha_is_never_recloned(self, origin: tuple[str, Path], tmp_path: Path, mocker: MockerFixture):
        clone_url, repo = origin
        head_sha = _git("rev-parse", "HEAD", cwd=repo)
        cache = MethodCloneCache(root_dir=tmp_path / "cache")
        fetch_spy = mocker.spy(cache, "_package_from_clone")
        clone_spy = mocker.patch("api.method_cache.fetch_method_package", wraps=fetch_method_package)

        first = cache.get_or_fetch(ref=_REF, clone_url=clone_url)
        second = cache.get_or_fetch(ref=_REF, clone_url=clone_url)

        assert clone_spy.call_count == 1, "the second request must be served from the cache"
        assert fetch_spy.call_count == 2, "location + bounds re-run on every request"
        assert first.commit_sha == head_sha
        assert second.commit_sha == head_sha
        assert first.package_dir == second.package_dir
        assert (tmp_path / "cache" / head_sha).is_dir()
        # Provenance is the honest record: address, tag, and the resolved SHA.
        assert first.provenance.address == "github.com/pipelex/methods/documents"
        assert first.provenance.tag == "v0.1.0"

    def test_a_moved_tag_resolves_to_a_fresh_clone(self, origin: tuple[str, Path], tmp_path: Path):
        clone_url, repo = origin
        cache = MethodCloneCache(root_dir=tmp_path / "cache")
        first = cache.get_or_fetch(ref=_REF, clone_url=clone_url)

        # Move the tag: a new commit, and v0.1.0 forced onto it. Never cache by tag alone —
        # the same reference must now fetch the NEW commit.
        (repo / "methods" / "documents" / "extra.mthds").write_text(VALID_MTHDS.replace('"smoke"', '"extra"'), encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-m", "move the tag", cwd=repo)
        _git("tag", "-f", "-a", "v0.1.0", "-m", "moved tag", cwd=repo)

        second = cache.get_or_fetch(ref=_REF, clone_url=clone_url)
        assert second.commit_sha != first.commit_sha
        assert (tmp_path / "cache" / first.commit_sha).is_dir()
        assert (tmp_path / "cache" / second.commit_sha).is_dir()

    def test_count_bound_evicts_oldest_keeping_newest(self, origin: tuple[str, Path], tmp_path: Path, mocker: MockerFixture):
        clone_url, repo = origin
        mocker.patch("api.method_cache.MAX_METHOD_CACHE_CLONES", 1)
        cache = MethodCloneCache(root_dir=tmp_path / "cache")
        first = cache.get_or_fetch(ref=_REF, clone_url=clone_url)

        (repo / "methods" / "documents" / "extra.mthds").write_text(VALID_MTHDS.replace('"smoke"', '"extra"'), encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-m", "second version", cwd=repo)
        _git("tag", "-a", "v0.2.0", "-m", "second tag", cwd=repo)
        # Make the first entry visibly older than the newcomer (mtime is the eviction order).
        old = time.time() - 120
        os.utime(tmp_path / "cache" / first.commit_sha, (old, old))

        second_ref = parse_method_ref("github.com/pipelex/methods/documents@v0.2.0")
        second = cache.get_or_fetch(ref=second_ref, clone_url=clone_url)

        assert not (tmp_path / "cache" / first.commit_sha).exists(), "the oldest entry is evicted past the count bound"
        assert (tmp_path / "cache" / second.commit_sha).is_dir(), "the newest entry always survives"

    def test_age_bound_evicts_stale_entries(self, origin: tuple[str, Path], tmp_path: Path, mocker: MockerFixture):
        clone_url, repo = origin
        mocker.patch("api.method_cache.MAX_METHOD_CACHE_AGE_SECONDS", 3600)
        cache = MethodCloneCache(root_dir=tmp_path / "cache")
        first = cache.get_or_fetch(ref=_REF, clone_url=clone_url)
        stale = time.time() - 7200
        os.utime(tmp_path / "cache" / first.commit_sha, (stale, stale))

        (repo / "methods" / "documents" / "extra.mthds").write_text(VALID_MTHDS.replace('"smoke"', '"extra"'), encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-m", "second version", cwd=repo)
        _git("tag", "-a", "v0.2.0", "-m", "second tag", cwd=repo)
        second_ref = parse_method_ref("github.com/pipelex/methods/documents@v0.2.0")
        second = cache.get_or_fetch(ref=second_ref, clone_url=clone_url)

        assert not (tmp_path / "cache" / first.commit_sha).exists(), "an entry unused past the age bound is evicted"
        assert (tmp_path / "cache" / second.commit_sha).is_dir()

    def test_nonexistent_repository_is_a_fetch_error(self, tmp_path: Path):
        with pytest.raises(MethodFetchError, match="could not reach the repository"):
            resolve_remote_commit_sha(ref=_BARE_REF, clone_url=f"file://{tmp_path}/no-such-repo")
