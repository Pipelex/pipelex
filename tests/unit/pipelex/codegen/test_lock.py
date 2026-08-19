"""The codegen lock: build/encode/load round-trip, deterministic ordering, and malformed-lock handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.codegen.exceptions import CodegenLockError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, CODEGEN_LOCK_VERSION, build_lock, encode_lock, load_lock

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


_LEGACY_LOCK_WITHOUT_VERSION = """\
crate_fingerprint = "fp-abc"
engine_version = "2.1.0"

[[artifacts]]
path = "models.py"
content_hash = "h1"

[[artifacts]]
path = "types.ts"
content_hash = "h2"
"""
"""A `codegen.lock` exactly as it was written before `lock_version` existed — verbatim, never regenerated."""


class TestLock:
    def test_build_sorts_artifacts_by_path(self) -> None:
        lock = build_lock(crate_fingerprint="fp", engine_version="1.0.0", artifacts={"z.ts": "hz", "a.py": "ha"})
        assert [entry.path for entry in lock.artifacts] == ["a.py", "z.ts"]
        assert lock.hash_by_path() == {"a.py": "ha", "z.ts": "hz"}
        assert lock.paths() == {"a.py", "z.ts"}

    def test_encode_then_load_round_trips(self, tmp_path: Path) -> None:
        lock = build_lock(crate_fingerprint="fp-abc", engine_version="2.1.0", artifacts={"models.py": "h1", "types.ts": "h2"})
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(encode_lock(lock), encoding="utf-8")
        loaded = load_lock(lock_path)
        assert loaded is not None
        assert loaded.crate_fingerprint == "fp-abc"
        assert loaded.engine_version == "2.1.0"
        assert loaded.hash_by_path() == {"models.py": "h1", "types.ts": "h2"}

    def test_load_absent_lock_is_none(self, tmp_path: Path) -> None:
        assert load_lock(tmp_path / CODEGEN_LOCK_FILENAME) is None

    def test_malformed_lock_raises(self, tmp_path: Path) -> None:
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text("this is not = valid = toml [[", encoding="utf-8")
        with pytest.raises(CodegenLockError):
            load_lock(lock_path)

    def test_non_utf8_lock_raises_clean_error_not_a_crash(self, tmp_path: Path) -> None:
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_bytes(b"\xff\xfe not valid utf-8")
        with pytest.raises(CodegenLockError):
            load_lock(lock_path)

    def test_unreadable_lock_raises_clean_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text("crate_fingerprint = 'fp'", encoding="utf-8")
        mocker.patch("pipelex.codegen.lock.load_text_from_path", side_effect=PermissionError("permission denied"))

        with pytest.raises(CodegenLockError, match="permission denied"):
            load_lock(lock_path)

    def test_encoded_lock_declares_its_format_version_first(self) -> None:
        """The version must be the first key a reader meets, so a wrong-version lock is diagnosable at a glance."""
        lock = build_lock(crate_fingerprint="fp", engine_version="1.0.0", artifacts={"a.py": "ha"})
        encoded = encode_lock(lock)
        assert f"lock_version = {CODEGEN_LOCK_VERSION}" in encoded
        assert encoded.index("lock_version") < encoded.index("crate_fingerprint")

    def test_round_trip_preserves_the_format_version(self, tmp_path: Path) -> None:
        lock = build_lock(crate_fingerprint="fp", engine_version="1.0.0", artifacts={"a.py": "ha"})
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(encode_lock(lock), encoding="utf-8")
        loaded = load_lock(lock_path)
        assert loaded is not None
        assert loaded.lock_version == CODEGEN_LOCK_VERSION

    def test_a_lock_written_before_the_version_field_loads_as_version_one(self, tmp_path: Path) -> None:
        """The no-migration guarantee: every lock already on disk predates the field and must still load."""
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(_LEGACY_LOCK_WITHOUT_VERSION, encoding="utf-8")

        loaded = load_lock(lock_path)

        assert loaded is not None
        assert loaded.lock_version == 1
        assert loaded.hash_by_path() == {"models.py": "h1", "types.ts": "h2"}

    def test_a_newer_lock_version_is_refused_with_upgrade_guidance(self, tmp_path: Path) -> None:
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(f"lock_version = 2\n{_LEGACY_LOCK_WITHOUT_VERSION}", encoding="utf-8")

        with pytest.raises(CodegenLockError, match="upgrade pipelex") as exc_info:
            load_lock(lock_path)
        assert "2" in str(exc_info.value)
        # Reported on its own terms: a lock from a newer build is not malformed, and saying so would
        # bury the one instruction the reader can act on.
        assert "Malformed" not in str(exc_info.value)

    def test_a_newer_lock_version_is_refused_even_when_it_carries_unknown_keys(self, tmp_path: Path) -> None:
        """The whole point of versioning the format: the version verdict must outrank the strict key set.

        `extra="forbid"` would otherwise reject a future lock as a shape error before its version was ever
        read, so the reader would report an opaque pydantic complaint instead of "upgrade pipelex" — which
        is precisely the unactionable no-verdict CI failure this field exists to prevent.
        """
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(f'lock_version = 2\nfuture_key = "whatever"\n{_LEGACY_LOCK_WITHOUT_VERSION}', encoding="utf-8")

        with pytest.raises(CodegenLockError, match="upgrade pipelex"):
            load_lock(lock_path)

    @pytest.mark.parametrize("raw_version", ["0", "-1", '"two"', "1.5", "true"])
    def test_a_lock_version_that_is_not_a_known_version_is_refused(self, tmp_path: Path, raw_version: str) -> None:
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(f"lock_version = {raw_version}\n{_LEGACY_LOCK_WITHOUT_VERSION}", encoding="utf-8")

        with pytest.raises(CodegenLockError):
            load_lock(lock_path)
