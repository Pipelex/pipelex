"""The stamped-projection writer: stamping, write-if-changed idempotence, de-listed pruning, and locking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.codegen.emission import WriteReport, write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, load_lock
from pipelex.codegen.stamp import has_stamp

if TYPE_CHECKING:
    from pathlib import Path

_FILES = [
    EmittedFile(filename="models.py", content="# h\nclass A:\n    pass\n"),
    EmittedFile(filename="types.ts", content="// h\nexport type A = number;\n"),
]


class TestEmission:
    def _write(self, root: Path, *, fingerprint: str = "fp1", files: list[EmittedFile] | None = None) -> WriteReport:
        return write_stamped_projection(
            files if files is not None else _FILES,
            output_dir=root,
            crate_fingerprint=fingerprint,
            engine_version="0.1.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )

    def test_first_write_stamps_every_file_and_writes_the_lock(self, tmp_path: Path) -> None:
        report = self._write(tmp_path)
        assert set(report.written) == {"models.py", "types.ts"}
        assert report.unchanged == []
        assert has_stamp((tmp_path / "models.py").read_text(encoding="utf-8"), comment_prefix="#")
        lock = load_lock(tmp_path / CODEGEN_LOCK_FILENAME)
        assert lock is not None
        assert lock.crate_fingerprint == "fp1"
        assert lock.paths() == {"models.py", "types.ts"}

    def test_body_is_preserved_below_the_stamp(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        assert (tmp_path / "models.py").read_text(encoding="utf-8").endswith("# h\nclass A:\n    pass\n")

    def test_rewriting_identical_input_is_all_unchanged(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        report = self._write(tmp_path)
        assert report.written == []
        assert set(report.unchanged) == {"models.py", "types.ts"}

    def test_delisted_stamped_file_is_pruned_and_delocked(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        # Regenerate producing only models.py: types.ts drops out and is removed, lock no longer tracks it.
        report = self._write(tmp_path, fingerprint="fp2", files=[_FILES[0]])
        assert report.removed == ["types.ts"]
        assert not (tmp_path / "types.ts").exists()
        lock = load_lock(tmp_path / CODEGEN_LOCK_FILENAME)
        assert lock is not None
        assert lock.paths() == {"models.py"}
        assert lock.crate_fingerprint == "fp2"

    def test_pruning_never_touches_an_unstamped_file(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        # A hand-authored file sharing a tracked name is replaced by a stamped one only via regeneration;
        # a file the lock tracks but that lost its stamp must NOT be deleted by the pruner.
        (tmp_path / "types.ts").write_text("// hand authored, no stamp\n", encoding="utf-8")
        report = self._write(tmp_path, fingerprint="fp2", files=[_FILES[0]])
        assert report.removed == []
        assert (tmp_path / "types.ts").exists()
