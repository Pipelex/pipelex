"""The offline drift check: clean, missing, modified, hand-edited, and orphan verdicts, plus no-lock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.codegen.check import DriftCategory, run_codegen_check
from pipelex.codegen.emission import build_stamped_projection, write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile

if TYPE_CHECKING:
    from pathlib import Path

_FILES = [
    EmittedFile(filename="models.py", content="# h\nclass A:\n    pass\n"),
    EmittedFile(filename="types.ts", content="// h\nexport type A = number;\n"),
]


class TestCheck:
    def _generate(self, root: Path, *, fingerprint: str = "fp1", files: list[EmittedFile] | None = None) -> None:
        write_stamped_projection(
            files if files is not None else _FILES,
            output_dir=root,
            crate_fingerprint=fingerprint,
            engine_version="0.1.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )

    def test_no_lock_is_no_verdict(self, tmp_path: Path) -> None:
        report = run_codegen_check(root=tmp_path)
        assert report.lock_found is False
        assert report.is_current is False

    def test_freshly_generated_is_current(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        report = run_codegen_check(root=tmp_path)
        assert report.is_current
        assert report.drifts == []

    def test_deleted_file_is_missing_drift(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        (tmp_path / "types.ts").unlink()
        report = run_codegen_check(root=tmp_path)
        assert not report.is_current
        assert [(d.path, d.category) for d in report.drifts] == [("types.ts", DriftCategory.MISSING)]

    def test_hand_edit_below_stamp_is_hand_edited_drift(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        target = tmp_path / "models.py"
        target.write_text(target.read_text(encoding="utf-8") + "sneaky = 1\n", encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert any(d.path == "models.py" and d.category == DriftCategory.HAND_EDITED for d in report.drifts)

    def test_stripped_stamp_is_hand_edited_drift(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        target = tmp_path / "models.py"
        target.write_text("class A:\n    pass\n", encoding="utf-8")  # stamp header removed entirely
        report = run_codegen_check(root=tmp_path)
        assert any(d.path == "models.py" and d.category == DriftCategory.HAND_EDITED for d in report.drifts)

    def test_malformed_stamp_options_are_hand_edited_drift(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        target = tmp_path / "models.py"
        target.write_text(target.read_text(encoding="utf-8").replace("# options: {}", "# options: {bad"), encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert any(d.path == "models.py" and d.category == DriftCategory.HAND_EDITED for d in report.drifts)

    def test_stale_stamped_file_not_in_lock_is_orphan(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        # Copy a stamped file under a new name: it carries a stamp but the lock does not track it.
        (tmp_path / "stray.py").write_text((tmp_path / "models.py").read_text(encoding="utf-8"), encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert any(d.path == "stray.py" and d.category == DriftCategory.ORPHAN for d in report.drifts)

    def test_unstamped_sibling_file_is_ignored(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        (tmp_path / "hand_written.py").write_text("x = 1\n", encoding="utf-8")  # no stamp -> not our artifact
        report = run_codegen_check(root=tmp_path)
        assert report.is_current

    def test_non_utf8_tracked_file_is_hand_edited_not_a_crash(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        (tmp_path / "models.py").write_bytes(b"\xff\xfe not valid utf-8")
        report = run_codegen_check(root=tmp_path)  # must not raise
        assert any(d.path == "models.py" and d.category == DriftCategory.HAND_EDITED for d in report.drifts)

    def test_non_utf8_stray_file_is_ignored_not_a_crash(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        (tmp_path / "legacy.py").write_bytes(b"# caf\xe9\n")  # latin-1 bytes, unrelated file
        report = run_codegen_check(root=tmp_path)  # orphan scan must not choke on it
        assert report.is_current

    def test_orphan_scan_prunes_vendor_directories(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        # A stamped file buried in a vendor dir must not be flagged as an orphan (the scan prunes it).
        vendor = tmp_path / "node_modules" / "pkg"
        vendor.mkdir(parents=True)
        (vendor / "types.ts").write_text((tmp_path / "models.py").read_text(encoding="utf-8"), encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert report.is_current

    def test_nested_stamped_orphan_is_detected(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        nested = tmp_path / "sub" / "deep"
        nested.mkdir(parents=True)
        (nested / "stray.py").write_text((tmp_path / "models.py").read_text(encoding="utf-8"), encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert any(d.path == "sub/deep/stray.py" and d.category == DriftCategory.ORPHAN for d in report.drifts)

    def _restamp_without_relocking(self, root: Path, *, filename: str, content: str) -> None:
        """Write a stamped, self-consistent artifact while leaving the lock alone — i.e. a `modified` drift."""
        projection = build_stamped_projection(
            [EmittedFile(filename=filename, content=content)],
            crate_fingerprint="fp1",
            engine_version="0.1.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )
        (root / filename).write_text(projection.files[0].content, encoding="utf-8")

    def test_uncommented_line_injected_into_the_header_is_hand_edited_drift(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        target = tmp_path / "models.py"
        # The injected line sits above the end marker, so the body below it — and its hash — are
        # untouched: without the header gate the file verifies as pristine.
        target.write_text(target.read_text(encoding="utf-8").replace("# options: {}", "sneaky = 1\n# options: {}"), encoding="utf-8")
        report = run_codegen_check(root=tmp_path)
        assert [(d.path, d.category) for d in report.drifts] == [("models.py", DriftCategory.HAND_EDITED)]

    def test_drifts_are_ordered_locked_first_then_orphans_each_by_path(self, tmp_path: Path) -> None:
        self._generate(tmp_path)
        # Two locked drifts: a body that no longer matches the lock, and a deleted artifact.
        self._restamp_without_relocking(tmp_path, filename="models.py", content="# h\nclass B:\n    pass\n")
        (tmp_path / "types.ts").unlink()
        # Two orphans forming the adversarial pair: component-wise `sub/` precedes `sub.py`, string-wise
        # `sub.py` precedes `sub/foo.py` because '.' sorts before '/'.
        stamped = (tmp_path / "models.py").read_text(encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "foo.py").write_text(stamped, encoding="utf-8")
        (tmp_path / "sub.py").write_text(stamped, encoding="utf-8")

        report = run_codegen_check(root=tmp_path)

        # `types.ts` sorts after both orphans yet comes first: the locked loop is reported before the
        # orphan loop, and each loop is ordered by the plain full-string path sort.
        assert [(d.path, d.category) for d in report.drifts] == [
            ("models.py", DriftCategory.MODIFIED),
            ("types.ts", DriftCategory.MISSING),
            ("sub.py", DriftCategory.ORPHAN),
            ("sub/foo.py", DriftCategory.ORPHAN),
        ]
