"""Regression tests for autofix's optimistic, atomic file commit."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.pipeline.exceptions import FixWriteConflictError
from pipelex.pipeline.fixes.fix_loop import (
    _commit_file_updates,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _PendingFileUpdate,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _read_file_snapshot,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
)


class TestFixFileTransaction:
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
        first_path.write_text("first original\n", encoding="utf-8")
        second_path.write_text("second original\n", encoding="utf-8")
        updates = [
            _PendingFileUpdate(snapshot=_read_file_snapshot(first_path), new_content="first fixed\n"),
            _PendingFileUpdate(snapshot=_read_file_snapshot(second_path), new_content="second fixed\n"),
        ]
        original_replace = Path.replace
        replacement_count = 0

        def fail_second_replacement(source_path: Path, target_path: Path) -> Path:
            nonlocal replacement_count
            if ".pipelex-fix-new." in source_path.name:
                replacement_count += 1
                if replacement_count == 2:
                    msg = "second replace failed"
                    raise OSError(msg)
            return original_replace(source_path, target_path)

        mocker.patch.object(Path, "replace", new=fail_second_replacement)

        with pytest.raises(OSError, match="second replace failed"):
            _commit_file_updates(updates)

        assert first_path.read_text(encoding="utf-8") == "first original\n"
        assert second_path.read_text(encoding="utf-8") == "second original\n"
        assert list(tmp_path.glob(".*.pipelex-fix-*.tmp")) == []
