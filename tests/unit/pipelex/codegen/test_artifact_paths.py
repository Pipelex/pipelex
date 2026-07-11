from pathlib import Path

import pytest

from pipelex.codegen.check import run_codegen_check
from pipelex.codegen.emission import StampedProjection, WriteReport, build_stamped_projection, write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget, EmittedFile
from pipelex.codegen.exceptions import CodegenError, CodegenLockError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME, validate_artifact_path
from tests.unit.pipelex.codegen.test_data import ArtifactPathCases

_FILES = [EmittedFile(filename="models.py", content="class Model:\n    pass\n")]


class TestArtifactPaths:
    @pytest.mark.parametrize("artifact_path", ArtifactPathCases.INVALID_PATHS)
    def test_invalid_artifact_paths_are_rejected(self, artifact_path: str) -> None:
        with pytest.raises(CodegenError):
            validate_artifact_path(artifact_path)

    def test_valid_nested_artifact_stays_beneath_root(self, tmp_path: Path) -> None:
        nested_file = EmittedFile(filename="generated/models.py", content="class Model:\n    pass\n")

        self._write(tmp_path, files=[nested_file])

        assert (tmp_path / "generated" / "models.py").is_file()
        assert run_codegen_check(root=tmp_path).is_current

    def test_duplicate_emitted_paths_are_rejected(self) -> None:
        duplicate = EmittedFile(filename="models.py", content="different = True\n")

        with pytest.raises(CodegenError, match="Duplicate"):
            self._build([_FILES[0], duplicate])

    def test_traversal_cannot_write_outside_output_root(self, tmp_path: Path) -> None:
        output_root = tmp_path / "output"
        traversal = EmittedFile(filename="../escaped.py", content="escaped = True\n")

        with pytest.raises(CodegenError):
            self._write(output_root, files=[traversal])

        assert not (tmp_path / "escaped.py").exists()

    def test_malicious_lock_cannot_delete_outside_output_root(self, tmp_path: Path) -> None:
        output_root = tmp_path / "output"
        output_root.mkdir()
        victim = tmp_path / "victim.py"
        victim.write_text("# generated-looking victim\n", encoding="utf-8")
        self._write_raw_lock(output_root, paths=("../victim.py",))

        with pytest.raises(CodegenLockError):
            self._write(output_root, files=[])

        assert victim.read_text(encoding="utf-8") == "# generated-looking victim\n"

    def test_duplicate_lock_paths_are_rejected(self, tmp_path: Path) -> None:
        self._write_raw_lock(tmp_path, paths=("models.py", "models.py"))

        with pytest.raises(CodegenLockError, match="Duplicate"):
            run_codegen_check(root=tmp_path)

    def test_symlink_destination_cannot_redirect_a_write(self, tmp_path: Path) -> None:
        output_root = tmp_path / "output"
        output_root.mkdir()
        target = tmp_path / "target.py"
        target.write_text("keep = True\n", encoding="utf-8")
        self._make_symlink(output_root / "models.py", target=target)

        with pytest.raises(CodegenError, match="symbolic link"):
            self._write(output_root)

        assert target.read_text(encoding="utf-8") == "keep = True\n"

    def test_symlinked_parent_cannot_redirect_a_nested_write(self, tmp_path: Path) -> None:
        output_root = tmp_path / "output"
        output_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        self._make_symlink(output_root / "generated", target=outside, target_is_directory=True)
        nested_file = EmittedFile(filename="generated/models.py", content="escaped = True\n")

        with pytest.raises(CodegenError, match="symbolic link"):
            self._write(output_root, files=[nested_file])

        assert not (outside / "models.py").exists()

    def test_symlinked_output_root_is_rejected(self, tmp_path: Path) -> None:
        actual_root = tmp_path / "actual"
        actual_root.mkdir()
        output_root = tmp_path / "output"
        self._make_symlink(output_root, target=actual_root, target_is_directory=True)

        with pytest.raises(CodegenError, match="symbolic link"):
            self._write(output_root)

        assert not (actual_root / "models.py").exists()

    def test_codegen_check_does_not_read_a_symlinked_locked_artifact(self, tmp_path: Path) -> None:
        self._write(tmp_path)
        (tmp_path / "models.py").unlink()
        outside = tmp_path / "outside.py"
        outside.write_text("outside = True\n", encoding="utf-8")
        self._make_symlink(tmp_path / "models.py", target=outside)

        with pytest.raises(CodegenLockError, match="symbolic link"):
            run_codegen_check(root=tmp_path)

    def test_orphan_scan_does_not_descend_through_directory_symlinks(self, tmp_path: Path) -> None:
        output_root = tmp_path / "output"
        self._write(output_root)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "stray.py").write_text((output_root / "models.py").read_text(encoding="utf-8"), encoding="utf-8")
        self._make_symlink(output_root / "linked", target=outside, target_is_directory=True)

        assert run_codegen_check(root=output_root).is_current

    @staticmethod
    def _make_symlink(link_path: Path, *, target: Path, target_is_directory: bool = False) -> None:
        try:
            link_path.symlink_to(target, target_is_directory=target_is_directory)
        except OSError as exc:
            pytest.skip(f"Symbolic links are unavailable: {exc}")

    @staticmethod
    def _write_raw_lock(root: Path, *, paths: tuple[str, ...]) -> None:
        artifacts = "\n".join(f'[[artifacts]]\npath = "{path}"\ncontent_hash = "hash-{index}"' for index, path in enumerate(paths))
        content = f'crate_fingerprint = "fp"\nengine_version = "1"\n\n{artifacts}\n'
        (root / CODEGEN_LOCK_FILENAME).write_text(content, encoding="utf-8")

    @staticmethod
    def _build(files: list[EmittedFile]) -> StampedProjection:
        return build_stamped_projection(
            files,
            crate_fingerprint="fp",
            engine_version="1",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )

    @staticmethod
    def _write(root: Path, *, files: list[EmittedFile] | None = None) -> WriteReport:
        return write_stamped_projection(
            _FILES if files is None else files,
            output_dir=root,
            crate_fingerprint="fp",
            engine_version="1",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
        )
