from pathlib import Path

import pytest

from pipelex.pipeline.validate_bundle import dirs_beside_method


class TestDirsBesideMethod:
    def test_the_folder_is_left_out_however_it_is_spelled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Compared resolved: a relative spelling, an absolute one and a symbolic link all name the folder."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        other_dir = tmp_path / "libs"
        other_dir.mkdir()
        linked_dir = tmp_path / "linked"
        linked_dir.symlink_to(method_dir, target_is_directory=True)
        monkeypatch.chdir(tmp_path)

        beside = dirs_beside_method(method_dir=Path("method"), library_dirs=[method_dir, linked_dir, Path("libs"), Path("method")])

        assert beside == [Path("libs")]

    @pytest.mark.parametrize("library_dirs", [None, []], ids=["none", "empty"])
    def test_no_library_directory_leaves_nothing_beside(self, tmp_path: Path, library_dirs: list[Path] | None) -> None:
        assert dirs_beside_method(method_dir=tmp_path, library_dirs=library_dirs) == []
