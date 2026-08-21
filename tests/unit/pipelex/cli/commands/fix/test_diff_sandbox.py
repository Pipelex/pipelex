"""Unit tests for the ``--diff`` temp-copy sandbox (mirror + copy→original mapping)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.commands.fix._diff_sandbox import mirror_bundle_for_preview

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestDiffSandbox:
    def _sandbox_root(self, tmp_path: Path) -> Path:
        sandbox_root = tmp_path / "sandbox"
        sandbox_root.mkdir()
        return sandbox_root

    def test_entry_only_copies_entry_with_frozen_empty_load_scope(self, tmp_path: Path) -> None:
        entry = tmp_path / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=None, sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.entry_path != entry.resolve()
        assert sandbox.entry_path.read_text(encoding="utf-8") == 'domain = "demo"\n'
        assert sandbox.library_dirs == []
        assert sandbox.writable_library_dirs == []
        assert sandbox.to_original(str(sandbox.entry_path)) == str(entry.resolve())

    def test_explicit_empty_dirs_stay_empty(self, tmp_path: Path) -> None:
        entry = tmp_path / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs == []
        assert sandbox.writable_library_dirs == []

    def test_entry_under_library_dir_maps_inside_the_dir_copy(self, tmp_path: Path) -> None:
        """Directory mode: the sandbox entry must be the file INSIDE the mirrored dir, or pipes load twice."""
        bundle_dir = tmp_path / "pipeline_01"
        bundle_dir.mkdir()
        entry = bundle_dir / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        (bundle_dir / "sibling.mthds").write_text('domain = "sibling"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[bundle_dir], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        copy_dir = sandbox.library_dirs[0]
        assert sandbox.entry_path == copy_dir / "bundle.mthds"
        assert (copy_dir / "sibling.mthds").is_file()
        assert sandbox.to_original(str(copy_dir / "sibling.mthds")) == str((bundle_dir / "sibling.mthds").resolve())
        assert sandbox.writable_library_dirs == [copy_dir]

    def test_equivalent_explicit_dirs_share_one_canonical_copy(self, tmp_path: Path) -> None:
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        entry = bundle_dir / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(
            entry,
            library_dirs=[bundle_dir, bundle_dir / "."],
            sandbox_root=self._sandbox_root(tmp_path),
        )

        assert sandbox.library_dirs is not None
        assert len(sandbox.library_dirs) == 1
        assert sandbox.writable_library_dirs == sandbox.library_dirs

    def test_ambient_entry_uses_same_read_only_canonical_copy(self, tmp_path: Path, mocker: MockerFixture) -> None:
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        entry = bundle_dir / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        mocker.patch(
            "pipelex.cli.commands.fix._diff_sandbox.resolve_library_dirs",
            return_value=([bundle_dir], "PIPELEXPATH"),
        )

        sandbox = mirror_bundle_for_preview(entry, library_dirs=None, sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        assert sandbox.entry_path == sandbox.library_dirs[0] / entry.name
        assert sandbox.writable_library_dirs == []

    def test_entry_outside_library_dirs_gets_standalone_copy(self, tmp_path: Path) -> None:
        entry = tmp_path / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        libs_dir = tmp_path / "libs"
        libs_dir.mkdir()
        (libs_dir / "helper.mthds").write_text('domain = "helper"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[libs_dir], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        assert sandbox.entry_path.read_text(encoding="utf-8") == 'domain = "demo"\n'
        assert not sandbox.entry_path.is_relative_to(sandbox.library_dirs[0])
        assert sandbox.to_original(str(sandbox.entry_path)) == str(entry.resolve())
        assert sandbox.to_original(str(sandbox.library_dirs[0] / "helper.mthds")) == str((libs_dir / "helper.mthds").resolve())

    def test_missing_library_dir_mirrors_as_empty_copy_without_crashing(self, tmp_path: Path) -> None:
        """A non-existent -L dir must not crash copytree: the real loader skips it, so the sandbox mirrors it as an empty dir."""
        entry = tmp_path / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        missing_dir = tmp_path / "typo_dir"

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[missing_dir], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        # The missing dir is preserved 1:1 (so is_single_file matches the real run) as an empty copy.
        copy_dir = sandbox.library_dirs[0]
        assert copy_dir.is_dir()
        assert list(copy_dir.iterdir()) == []
        # The entry lives outside the missing dir, so it gets a standalone copy.
        assert sandbox.entry_path.read_text(encoding="utf-8") == 'domain = "demo"\n'
        assert sandbox.to_original(str(copy_dir / "would_be.mthds")) == str((missing_dir / "would_be.mthds").resolve())

    def test_paths_outside_the_sandbox_pass_through(self, tmp_path: Path) -> None:
        entry = tmp_path / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        ambient_file = tmp_path / "ambient.mthds"
        ambient_file.write_text('domain = "ambient"\n', encoding="utf-8")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=None, sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.to_original(str(ambient_file)) == str(ambient_file.resolve())

    def test_copy_uses_loader_exclusions(self, tmp_path: Path) -> None:
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        entry = bundle_dir / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        excluded_dir = bundle_dir / ".venv"
        excluded_dir.mkdir()
        (excluded_dir / "large.bin").write_bytes(b"must not be copied")

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[bundle_dir], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        assert not (sandbox.library_dirs[0] / ".venv").exists()

    def test_copy_preserves_external_directory_symlink(self, tmp_path: Path) -> None:
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        entry = bundle_dir / "bundle.mthds"
        entry.write_text('domain = "demo"\n', encoding="utf-8")
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        (external_dir / "large.bin").write_bytes(b"must not be copied")
        (bundle_dir / "linked").symlink_to(external_dir, target_is_directory=True)

        sandbox = mirror_bundle_for_preview(entry, library_dirs=[bundle_dir], sandbox_root=self._sandbox_root(tmp_path))

        assert sandbox.library_dirs is not None
        copied_link = sandbox.library_dirs[0] / "linked"
        assert copied_link.is_symlink()
        assert copied_link.readlink() == external_dir
