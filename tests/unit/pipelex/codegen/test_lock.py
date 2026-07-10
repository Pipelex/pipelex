"""The codegen lock: build/encode/load round-trip, deterministic ordering, and malformed-lock handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.codegen.exceptions import CodegenLockError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, build_lock, encode_lock, load_lock

if TYPE_CHECKING:
    from pathlib import Path


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
