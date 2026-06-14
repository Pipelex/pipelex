import tempfile
from pathlib import Path

import pytest

from pipelex.tools.misc.diff import has_diff_dirs
from pipelex.tools.misc.file_utils import mirror_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestMirrorDir:
    def test_copies_new_file(self):
        """A file present only in the source is copied into the target."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "value = 1")
            target.mkdir()

            result = mirror_dir(source, target_dir=target)

            assert result.copied_files == ["config.toml"]
            assert result.deleted_files == []
            assert (target / "config.toml").read_text(encoding="utf-8") == "value = 1"

    def test_copies_changed_file(self):
        """A file whose content differs from the target is overwritten."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "value = 2")
            _write(target / "config.toml", "value = 1")

            result = mirror_dir(source, target_dir=target)

            assert result.copied_files == ["config.toml"]
            assert (target / "config.toml").read_text(encoding="utf-8") == "value = 2"

    def test_unchanged_file_not_copied(self):
        """A byte-identical file is left untouched and not reported as copied."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "value = 1")
            _write(target / "config.toml", "value = 1")

            result = mirror_dir(source, target_dir=target)

            assert result.has_changes is False
            assert result.copied_files == []

    def test_deletes_target_only_file(self):
        """A file present only in the target is deleted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            _write(target / "stale.toml", "obsolete")

            result = mirror_dir(source, target_dir=target)

            assert result.deleted_files == ["stale.toml"]
            assert not (target / "stale.toml").exists()

    def test_deletes_target_only_directory_subtree(self):
        """A directory present only in the target is removed; only its top level is recorded."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            _write(target / "stale_dir" / "nested" / "file.toml", "obsolete")

            result = mirror_dir(source, target_dir=target)

            assert result.deleted_dirs == ["stale_dir"]
            assert result.deleted_files == []
            assert not (target / "stale_dir").exists()

    def test_recursion_preserves_structure(self):
        """Nested source files are copied into matching target subdirectories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "inference" / "backends" / "openai.toml", "openai")
            _write(source / "inference" / "deck" / "llm.toml", "llm")
            target.mkdir()

            result = mirror_dir(source, target_dir=target)

            assert result.copied_files == ["inference/backends/openai.toml", "inference/deck/llm.toml"]
            assert (target / "inference" / "backends" / "openai.toml").read_text(encoding="utf-8") == "openai"
            assert (target / "inference" / "deck" / "llm.toml").read_text(encoding="utf-8") == "llm"

    def test_creates_empty_source_subdir(self):
        """An empty source subdirectory is recreated in the target and recorded as a change."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            (source / "empty_dir").mkdir(parents=True)
            target.mkdir()

            result = mirror_dir(source, target_dir=target)

            assert result.created_dirs == ["empty_dir"]
            assert result.has_changes is True
            assert (target / "empty_dir").is_dir()

    def test_dry_run_reports_created_dir_without_creating_it(self):
        """dry_run records an added empty source directory without creating it on disk."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            (source / "empty_dir").mkdir(parents=True)
            target.mkdir()

            result = mirror_dir(source, target_dir=target, dry_run=True)

            assert result.created_dirs == ["empty_dir"]
            assert result.has_changes is True
            assert not (target / "empty_dir").exists()

    def test_excluded_file_target_only_is_preserved(self):
        """An excluded file present only in the target is not deleted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            _write(target / "telemetry.project.toml", "kit-only template")

            result = mirror_dir(source, target_dir=target, exclude_files=frozenset({"telemetry.project.toml"}))

            assert result.deleted_files == []
            assert (target / "telemetry.project.toml").exists()

    def test_excluded_file_is_not_copied(self):
        """An excluded file present in the source is not copied into the target."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "telemetry.toml", "dogfood override")
            target.mkdir()

            result = mirror_dir(source, target_dir=target, exclude_files=frozenset({"telemetry.toml"}))

            assert result.copied_files == []
            assert not (target / "telemetry.toml").exists()

    def test_excluded_dir_target_only_is_preserved(self):
        """An excluded directory present only in the target is left untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            _write(target / "storage" / "cached.bin", "runtime data")

            result = mirror_dir(source, target_dir=target, exclude_dirs=frozenset({"storage"}))

            assert result.deleted_dirs == []
            assert (target / "storage" / "cached.bin").exists()

    def test_nested_excluded_dir_is_preserved(self):
        """An excluded directory nested under a synced directory is left untouched."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "inference" / "backends.toml", "backends")
            _write(target / "inference" / "traces" / "run.log", "trace")

            result = mirror_dir(source, target_dir=target, exclude_dirs=frozenset({"traces"}))

            assert result.deleted_dirs == []
            assert (target / "inference" / "traces" / "run.log").exists()

    def test_dry_run_reports_without_touching_filesystem(self):
        """dry_run reports the same changes but leaves the filesystem unchanged."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "new.toml", "fresh")
            _write(target / "stale.toml", "obsolete")

            result = mirror_dir(source, target_dir=target, dry_run=True)

            assert result.dry_run is True
            assert result.copied_files == ["new.toml"]
            assert result.deleted_files == ["stale.toml"]
            assert not (target / "new.toml").exists()
            assert (target / "stale.toml").exists()

    def test_creates_missing_target_dir(self):
        """A target directory that does not exist yet is created and populated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "value = 1")

            result = mirror_dir(source, target_dir=target)

            assert result.copied_files == ["config.toml"]
            assert (target / "config.toml").read_text(encoding="utf-8") == "value = 1"

    def test_handles_directory_to_file_flip(self):
        """A name that is a directory in the target but a file in the source is replaced."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "item", "now a file")
            _write(target / "item" / "nested.toml", "was a directory")

            result = mirror_dir(source, target_dir=target)

            assert result.deleted_dirs == ["item"]
            assert result.copied_files == ["item"]
            assert (target / "item").is_file()
            assert (target / "item").read_text(encoding="utf-8") == "now a file"

    def test_idempotent_and_symmetric_with_has_diff_dirs(self):
        """After a real mirror, a second run is a no-op and has_diff_dirs agrees."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            exclude_files = frozenset({"telemetry.toml"})
            exclude_dirs = frozenset({"storage"})

            _write(source / "config.toml", "value = 1")
            _write(source / "inference" / "backends.toml", "backends")
            _write(source / "telemetry.toml", "source-side excluded")
            # Target-side excluded entries that must survive the sync.
            _write(target / "telemetry.toml", "target-side excluded")
            _write(target / "storage" / "cached.bin", "runtime data")
            _write(target / "stale.toml", "obsolete")

            first = mirror_dir(source, target_dir=target, exclude_files=exclude_files, exclude_dirs=exclude_dirs)
            assert first.has_changes is True

            second = mirror_dir(source, target_dir=target, exclude_files=exclude_files, exclude_dirs=exclude_dirs)
            assert second.has_changes is False

            assert has_diff_dirs(source, dir2=target, exclude_files=exclude_files, exclude_dirs=exclude_dirs) is False
            assert (target / "telemetry.toml").read_text(encoding="utf-8") == "target-side excluded"
            assert (target / "storage" / "cached.bin").exists()
            assert not (target / "stale.toml").exists()

    def test_raises_when_source_missing(self):
        """A missing source raises FileNotFoundError before the delete pass touches the target."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "does_not_exist"
            target = Path(temp_dir) / "target"
            _write(target / "keep.toml", "precious")

            with pytest.raises(FileNotFoundError):
                mirror_dir(source, target_dir=target)

            assert (target / "keep.toml").read_text(encoding="utf-8") == "precious"

    def test_raises_when_source_is_a_file(self):
        """A source path that is a file raises NotADirectoryError without wiping the target."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.write_text("i am a file", encoding="utf-8")
            _write(target / "keep.toml", "precious")

            with pytest.raises(NotADirectoryError):
                mirror_dir(source, target_dir=target)

            assert (target / "keep.toml").read_text(encoding="utf-8") == "precious"

    def test_replaces_target_file_symlink(self):
        """A target file symlink is replaced with a real copy, leaving the file it pointed to intact."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "real config")
            external = Path(temp_dir) / "external.toml"
            external.write_text("external content", encoding="utf-8")
            target.mkdir()
            (target / "config.toml").symlink_to(external)

            result = mirror_dir(source, target_dir=target)

            assert result.copied_files == ["config.toml"]
            assert not (target / "config.toml").is_symlink()
            assert (target / "config.toml").read_text(encoding="utf-8") == "real config"
            # The stale symlink is replaced, but the file it pointed to is left untouched.
            assert external.read_text(encoding="utf-8") == "external content"

    def test_dry_run_reports_target_file_symlink_without_touching_filesystem(self):
        """dry_run reports a target file symlink as a change without unlinking or copying."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            _write(source / "config.toml", "real config")
            external = Path(temp_dir) / "external.toml"
            external.write_text("external content", encoding="utf-8")
            target.mkdir()
            (target / "config.toml").symlink_to(external)

            result = mirror_dir(source, target_dir=target, dry_run=True)

            assert result.copied_files == ["config.toml"]
            assert (target / "config.toml").is_symlink()
            assert external.read_text(encoding="utf-8") == "external content"

    def test_deletes_target_only_broken_file_symlink(self):
        """A target-only file symlink whose target no longer exists is unlinked, not just reported."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            external = Path(temp_dir) / "vanished.toml"
            external.write_text("temporary", encoding="utf-8")
            target.mkdir()
            (target / "stale_link.toml").symlink_to(external)
            # Make the symlink broken by removing the target it points to.
            external.unlink()

            result = mirror_dir(source, target_dir=target)

            assert result.deleted_files == ["stale_link.toml"]
            # The broken symlink itself must actually be gone from the target tree.
            assert not (target / "stale_link.toml").is_symlink()
            assert not (target / "stale_link.toml").exists()

    def test_deletes_target_only_directory_symlink(self):
        """A target-only directory symlink is unlinked instead of aborting the sync on rmtree."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            real_dir = Path(temp_dir) / "real_dir"
            _write(real_dir / "payload.toml", "data")
            target.mkdir()
            (target / "linked_dir").symlink_to(real_dir, target_is_directory=True)

            result = mirror_dir(source, target_dir=target)

            assert result.deleted_dirs == ["linked_dir"]
            assert not (target / "linked_dir").exists()
            # The symlink is removed, but its target directory is left intact.
            assert (real_dir / "payload.toml").read_text(encoding="utf-8") == "data"
