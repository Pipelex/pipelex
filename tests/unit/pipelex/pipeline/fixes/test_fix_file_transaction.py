"""Regression tests for autofix's optimistic, atomic file commit."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.pipeline.exceptions import FixTransactionError, FixWriteConflictError
from pipelex.pipeline.fixes.fix_loop import (
    _assert_snapshot_unchanged,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _bind_fixes_to_snapshots,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _commit_file_updates,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _FileSnapshot,  # pyright: ignore[reportPrivateUsage]
    _PendingFileUpdate,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _read_file_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _snapshot_loaded_sources,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
)
from pipelex.suggested_fix import FixSafety, SuggestedFix


class TestFixFileTransaction:
    def test_symlink_retarget_during_validation_is_rejected(self, tmp_path: Path) -> None:
        first_target = tmp_path / "first.mthds"
        second_target = tmp_path / "second.mthds"
        first_target.write_text("first\n", encoding="utf-8")
        second_target.write_text("second\n", encoding="utf-8")
        source_link = tmp_path / "library.mthds"
        source_link.symlink_to(first_target)
        snapshots = _snapshot_loaded_sources(entry_source_path=source_link, effective_dirs=[])
        fix = SuggestedFix(fix_code="test", description="test", safety=FixSafety.SAFE, source=str(source_link), ops=[])
        source_link.unlink()
        source_link.symlink_to(second_target)

        with pytest.raises(FixWriteConflictError, match="retargeted"):
            _bind_fixes_to_snapshots([fix], entry_source_path=source_link, snapshots_by_source=snapshots)

    def test_concurrent_edit_is_not_overwritten(self, tmp_path: Path) -> None:
        target = tmp_path / "bundle.mthds"
        target.write_text("original\n", encoding="utf-8")
        snapshot = _read_file_snapshot(target)
        target.write_text("user edit\n", encoding="utf-8")

        with pytest.raises(FixWriteConflictError, match="file changed"):
            _commit_file_updates([_PendingFileUpdate(snapshot=snapshot, new_content="fixed\n")])

        assert target.read_text(encoding="utf-8") == "user edit\n"
        assert list(tmp_path.glob(".*.pipelex-fix-*.tmp")) == []

    def test_failed_atomic_replace_preserves_original(self, tmp_path: Path, mocker: MockerFixture) -> None:
        target = tmp_path / "bundle.mthds"
        target.write_text("original\n", encoding="utf-8")
        snapshot = _read_file_snapshot(target)
        mocker.patch.object(Path, "replace", side_effect=OSError("replace failed"))

        with pytest.raises(OSError, match="replace failed"):
            _commit_file_updates([_PendingFileUpdate(snapshot=snapshot, new_content="fixed\n")])

        assert target.read_text(encoding="utf-8") == "original\n"
        assert list(tmp_path.glob(".*.pipelex-fix-*.tmp")) == []

    def test_multi_file_replace_failure_rolls_back_prior_targets(self, tmp_path: Path, mocker: MockerFixture) -> None:
        first_path = tmp_path / "first.mthds"
        second_path = tmp_path / "second.mthds"
        third_path = tmp_path / "third.mthds"
        first_path.write_text("first original\n", encoding="utf-8")
        second_path.write_text("second original\n", encoding="utf-8")
        third_path.write_text("third original\n", encoding="utf-8")
        updates = [
            _PendingFileUpdate(snapshot=_read_file_snapshot(first_path), new_content="first fixed\n"),
            _PendingFileUpdate(snapshot=_read_file_snapshot(second_path), new_content="second fixed\n"),
            _PendingFileUpdate(snapshot=_read_file_snapshot(third_path), new_content="third fixed\n"),
        ]
        original_replace = Path.replace
        replacement_count = 0
        rollback_targets: list[str] = []

        def fail_third_replacement(source_path: Path, target_path: Path) -> Path:
            nonlocal replacement_count
            if ".pipelex-fix-new." in source_path.name:
                replacement_count += 1
                if replacement_count == 3:
                    msg = "third replace failed"
                    raise OSError(msg)
            elif ".pipelex-fix-rollback." in source_path.name:
                rollback_targets.append(target_path.name)
            return original_replace(source_path, target_path)

        mocker.patch.object(Path, "replace", new=fail_third_replacement)

        with pytest.raises(OSError, match="third replace failed"):
            _commit_file_updates(updates)

        assert first_path.read_text(encoding="utf-8") == "first original\n"
        assert second_path.read_text(encoding="utf-8") == "second original\n"
        assert third_path.read_text(encoding="utf-8") == "third original\n"
        assert rollback_targets == ["second.mthds", "first.mthds"]
        assert list(tmp_path.glob(".*.pipelex-fix-*.tmp")) == []

    def test_rollback_does_not_overwrite_edit_after_prior_commit(self, tmp_path: Path, mocker: MockerFixture) -> None:
        first_path = tmp_path / "first.mthds"
        second_path = tmp_path / "second.mthds"
        third_path = tmp_path / "third.mthds"
        first_path.write_text("first original\n", encoding="utf-8")
        second_path.write_text("second original\n", encoding="utf-8")
        third_path.write_text("third original\n", encoding="utf-8")
        updates = [
            _PendingFileUpdate(snapshot=_read_file_snapshot(first_path), new_content="first fixed\n"),
            _PendingFileUpdate(snapshot=_read_file_snapshot(second_path), new_content="second fixed\n"),
            _PendingFileUpdate(snapshot=_read_file_snapshot(third_path), new_content="third fixed\n"),
        ]
        assertion_count = 0

        def inject_edit_before_third_commit(snapshot: _FileSnapshot) -> None:
            nonlocal assertion_count
            assertion_count += 1
            if assertion_count == 3:
                second_path.write_text("concurrent user edit\n", encoding="utf-8")
                msg = "injected third-file conflict"
                raise FixWriteConflictError(msg)
            _assert_snapshot_unchanged(snapshot)

        mocker.patch("pipelex.pipeline.fixes.fix_loop._assert_snapshot_unchanged", new=inject_edit_before_third_commit)

        with pytest.raises(FixTransactionError, match="rollback was incomplete") as exc_info:
            _commit_file_updates(updates)

        assert first_path.read_text(encoding="utf-8") == "first original\n"
        assert second_path.read_text(encoding="utf-8") == "concurrent user edit\n"
        assert third_path.read_text(encoding="utf-8") == "third original\n"
        assert str(second_path) in str(exc_info.value)
        assert "inspect the named files before retrying" in str(exc_info.value)
        assert list(tmp_path.glob(".*.pipelex-fix-*.tmp")) == []

    def test_cleanup_failure_reports_committed_outcome(self, tmp_path: Path, mocker: MockerFixture) -> None:
        target = tmp_path / "bundle.mthds"
        target.write_text("original\n", encoding="utf-8")
        snapshot = _read_file_snapshot(target)
        original_unlink = Path.unlink

        def fail_temp_cleanup(path: Path, *, missing_ok: bool = False) -> None:
            if ".pipelex-fix-rollback." in path.name:
                msg = "cleanup failed"
                raise OSError(msg)
            original_unlink(path, missing_ok=missing_ok)

        mocker.patch.object(Path, "unlink", new=fail_temp_cleanup)

        with pytest.raises(FixTransactionError, match=r"target changes were committed.*cleanup failed"):
            _commit_file_updates([_PendingFileUpdate(snapshot=snapshot, new_content="fixed\n")])

        assert target.read_text(encoding="utf-8") == "fixed\n"

    def test_cleanup_failure_does_not_mask_commit_failure(self, tmp_path: Path, mocker: MockerFixture) -> None:
        target = tmp_path / "bundle.mthds"
        target.write_text("original\n", encoding="utf-8")
        snapshot = _read_file_snapshot(target)

        mocker.patch.object(Path, "replace", side_effect=OSError("primary replace failure"))
        mocker.patch.object(Path, "unlink", side_effect=OSError("secondary cleanup failure"))

        with pytest.raises(OSError, match="primary replace failure") as exc_info:
            _commit_file_updates([_PendingFileUpdate(snapshot=snapshot, new_content="fixed\n")])

        assert target.read_text(encoding="utf-8") == "original\n"
        assert len(exc_info.value.__notes__) == 1
        assert "secondary cleanup failure" in exc_info.value.__notes__[0]
