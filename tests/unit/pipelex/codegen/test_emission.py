"""The stamped-projection writer: stamping, write-if-changed idempotence, de-listed pruning, and locking."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.codegen.check import DriftCategory, run_codegen_check
from pipelex.codegen.emission import WriteReport, build_stamped_projection, write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile
from pipelex.codegen.exceptions import CodegenError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, CODEGEN_LOCK_VERSION, load_lock
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

    def test_first_write_refuses_unowned_destination_without_partial_writes(self, tmp_path: Path) -> None:
        hand_authored = "// hand-authored module\n"
        (tmp_path / "types.ts").write_text(hand_authored, encoding="utf-8")

        with pytest.raises(CodegenError, match="Refusing to overwrite unowned file"):
            self._write(tmp_path)

        assert (tmp_path / "types.ts").read_text(encoding="utf-8") == hand_authored
        assert not (tmp_path / "models.py").exists()
        assert not (tmp_path / CODEGEN_LOCK_FILENAME).exists()

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

    def test_pure_build_and_disk_write_agree_byte_for_byte(self, tmp_path: Path) -> None:
        """The pure core and the writer must never drift: a host serving `build_stamped_projection`
        over the wire (the HTTP codegen route) hands out exactly the bytes a local
        `write_stamped_projection` run puts on disk — stamped artifacts and lock alike.
        """
        projection = build_stamped_projection(
            _FILES,
            crate_fingerprint="fp1",
            engine_version="0.1.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )
        self._write(tmp_path)
        for stamped_file in projection.files:
            assert (tmp_path / stamped_file.filename).read_text(encoding="utf-8") == stamped_file.content
        assert (tmp_path / CODEGEN_LOCK_FILENAME).read_text(encoding="utf-8") == projection.lock_content

    def test_pruning_never_touches_an_unstamped_file(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        # A hand-authored file sharing a tracked name is replaced by a stamped one only via regeneration;
        # a file the lock tracks but that lost its stamp must NOT be deleted by the pruner.
        (tmp_path / "types.ts").write_text("// hand authored, no stamp\n", encoding="utf-8")
        report = self._write(tmp_path, fingerprint="fp2", files=[_FILES[0]])
        assert report.removed == []
        assert (tmp_path / "types.ts").exists()

    def test_regeneration_recovers_from_a_malformed_previous_lock(self, tmp_path: Path) -> None:
        (tmp_path / CODEGEN_LOCK_FILENAME).write_text("not = valid = toml [[", encoding="utf-8")

        report = self._write(tmp_path)

        assert set(report.written) == {"models.py", "types.ts"}
        lock = load_lock(tmp_path / CODEGEN_LOCK_FILENAME)
        assert lock is not None
        assert lock.paths() == {"models.py", "types.ts"}

    def test_regeneration_over_a_lock_written_before_the_version_field_relocks_it_once(self, tmp_path: Path) -> None:
        """A tree locked by a pre-`lock_version` build keeps working: the old set is still read (so pruning
        is not lost), the lock gains the version key on the next write, and the tree checks out current.
        """
        self._write(tmp_path)
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        legacy_content = "".join(line for line in lock_path.read_text(encoding="utf-8").splitlines(keepends=True) if "lock_version" not in line)
        lock_path.write_text(legacy_content, encoding="utf-8")

        # Regenerate without types.ts: pruning proves the legacy artifact set was read, not discarded.
        report = self._write(tmp_path, fingerprint="fp2", files=[_FILES[0]])

        assert report.removed == ["types.ts"]
        lock = load_lock(lock_path)
        assert lock is not None
        assert lock.lock_version == CODEGEN_LOCK_VERSION
        assert lock.paths() == {"models.py"}
        assert run_codegen_check(root=tmp_path).is_current

    def test_regeneration_replaces_a_lock_written_by_a_newer_codegen(self, tmp_path: Path) -> None:
        """Deliberate: an unreadable-version lock is replaceable prior state, exactly like a corrupt one.

        Regeneration has already rewritten every artifact with *this* engine, so adopting this engine's
        lock version is the coherent outcome; refusing would strand the developer on a purely derived
        file. The one thing lost is pruning (the newer set cannot be trusted), and anything the newer
        engine emitted that this one does not surfaces loudly as an orphan on the very next check.
        """
        self._write(tmp_path)
        lock_path = tmp_path / CODEGEN_LOCK_FILENAME
        lock_path.write_text(lock_path.read_text(encoding="utf-8").replace("lock_version = 1", "lock_version = 99"), encoding="utf-8")

        report = self._write(tmp_path, fingerprint="fp2", files=[_FILES[0]])

        assert report.removed == []
        lock = load_lock(lock_path)
        assert lock is not None
        assert lock.lock_version == CODEGEN_LOCK_VERSION
        assert lock.paths() == {"models.py"}
        # types.ts survived unpruned and is now reported, rather than silently lingering.
        assert [(drift.path, drift.category) for drift in run_codegen_check(root=tmp_path).drifts] == [("types.ts", DriftCategory.ORPHAN)]

    def test_a_stamped_file_whose_header_was_tampered_is_an_orphan_the_regenerator_refuses_to_reclaim(self, tmp_path: Path) -> None:
        """The one seam the strict header gate opens: the check's "remove or regenerate" advice is half true.

        A stamped file the lock does not track is an orphan, and regenerating reclaims an ordinary one by
        overwriting it. But a file whose header carries an injected uncommented line no longer *parses* as
        stamped, so the writer cannot prove it owns it and refuses rather than clobbering something that may
        hold real work — the same conservatism that protects a hand-authored module sharing the output
        directory. `remove` is the half of the advice that always applies. Refusing is the deliberate
        direction; this pins it so it stays a decision rather than an accident.
        """
        source = tmp_path / "source"
        source.mkdir()
        self._write(source)
        stamped = (source / "models.py").read_text(encoding="utf-8")
        begin_marker, below = stamped.split("\n", 1)
        tampered = f'{begin_marker}\nraise SystemExit("injected")\n{below}'

        root = tmp_path / "root"
        root.mkdir()
        self._write(root, files=[_FILES[1]])
        (root / "models.py").write_text(tampered, encoding="utf-8")

        assert [(drift.path, drift.category) for drift in run_codegen_check(root=root).drifts] == [("models.py", DriftCategory.ORPHAN)]

        with pytest.raises(CodegenError, match="Refusing to overwrite unowned file"):
            self._write(root)
        assert (root / "models.py").read_text(encoding="utf-8") == tampered
