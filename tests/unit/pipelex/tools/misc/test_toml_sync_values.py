from pathlib import Path

import pytest

from pipelex.tools.misc.toml_sync import sync_toml_values

TARGET_CONTENT = """# Pipelex target config
# header comments must survive sync

title = "old-title"
timeout = 30  # seconds

[section]
key = 1

[section.sub]
deep = "old"  # nested comment
"""

SOURCE_CONTENT = """title = "new-title"
timeout = 30

[section]
key = 1

[section.sub]
deep = "new"
"""

SYNCED_TARGET_CONTENT = """# Pipelex target config
# header comments must survive sync

title = "new-title"
timeout = 30  # seconds

[section]
key = 1

[section.sub]
deep = "new"  # nested comment
"""


def write_pair(tmp_path: Path, source_content: str, target_content: str) -> tuple[Path, Path]:
    """Write source and target TOML files into tmp_path and return their paths."""
    source_path = tmp_path / "source.toml"
    target_path = tmp_path / "target.toml"
    source_path.write_text(source_content)
    target_path.write_text(target_content)
    return source_path, target_path


class TestSyncTomlValues:
    def test_happy_path_updates_values_and_preserves_comments(self, tmp_path: Path) -> None:
        """Differing values are updated in place while header comments, inline comments and blank lines all survive."""
        source_path, target_path = write_pair(tmp_path, SOURCE_CONTENT, TARGET_CONTENT)

        result = sync_toml_values(source_path, target_path=target_path)

        assert target_path.read_text() == SYNCED_TARGET_CONTENT
        assert result.updated_keys == ["title", "section.sub.deep"]
        assert result.unchanged_keys == ["timeout", "section.key"]
        assert result.updated_count == 2
        assert result.unchanged_count == 2
        assert [(change.key_path, change.old_value, change.new_value) for change in result.changes] == [
            ("title", "old-title", "new-title"),
            ("section.sub.deep", "old", "new"),
        ]

    def test_key_only_in_source_is_never_added_to_target(self, tmp_path: Path) -> None:
        """A key present in source but absent from target must not be created in the target."""
        source_path, target_path = write_pair(
            tmp_path,
            'shared = "from-source"\nsource_only = "intruder"\n',
            'shared = "from-target"\n',
        )

        result = sync_toml_values(source_path, target_path=target_path)

        target_text = target_path.read_text()
        assert "source_only" not in target_text
        assert target_text == 'shared = "from-source"\n'
        assert result.updated_keys == ["shared"]

    def test_key_only_in_target_stays_untouched_and_unchanged(self, tmp_path: Path) -> None:
        """A key present in target but absent from source keeps its value and lands in unchanged_keys."""
        source_path, target_path = write_pair(
            tmp_path,
            'shared = "same"\n',
            'shared = "same"\ntarget_only = "precious"  # do not lose\n',
        )

        result = sync_toml_values(source_path, target_path=target_path)

        assert target_path.read_text() == 'shared = "same"\ntarget_only = "precious"  # do not lose\n'
        assert result.updated_keys == []
        assert sorted(result.unchanged_keys) == ["shared", "target_only"]
        assert result.changes == []

    def test_dry_run_reports_changes_without_writing(self, tmp_path: Path) -> None:
        """With dry_run=True the result lists the would-be changes but the target bytes are untouched."""
        source_path, target_path = write_pair(tmp_path, SOURCE_CONTENT, TARGET_CONTENT)
        bytes_before = target_path.read_bytes()

        result = sync_toml_values(source_path, target_path=target_path, dry_run=True)

        assert target_path.read_bytes() == bytes_before
        assert result.updated_keys == ["title", "section.sub.deep"]
        assert [(change.key_path, change.old_value, change.new_value) for change in result.changes] == [
            ("title", "old-title", "new-title"),
            ("section.sub.deep", "old", "new"),
        ]

    def test_no_changes_means_no_rewrite(self, tmp_path: Path) -> None:
        """When every value already matches, the target file is not rewritten so formatting quirks survive byte-for-byte."""
        quirky_target = 'answer   =   42   # extra   spacing\n\n\n[section]\nkey="tight"'
        source_path, target_path = write_pair(tmp_path, 'answer = 42\n\n[section]\nkey = "tight"\n', quirky_target)
        bytes_before = target_path.read_bytes()

        result = sync_toml_values(source_path, target_path=target_path)

        assert target_path.read_bytes() == bytes_before
        assert result.updated_keys == []
        assert sorted(result.unchanged_keys) == ["answer", "section.key"]

    def test_sync_is_idempotent(self, tmp_path: Path) -> None:
        """A second sync after a first one that applied changes finds nothing to update and leaves the bytes identical."""
        source_path, target_path = write_pair(tmp_path, SOURCE_CONTENT, TARGET_CONTENT)

        first_result = sync_toml_values(source_path, target_path=target_path)
        bytes_after_first = target_path.read_bytes()

        second_result = sync_toml_values(source_path, target_path=target_path)

        assert first_result.updated_keys == ["title", "section.sub.deep"]
        assert second_result.updated_keys == []
        assert second_result.changes == []
        assert second_result.unchanged_keys == ["title", "timeout", "section.key", "section.sub.deep"]
        assert target_path.read_bytes() == bytes_after_first

    def test_nested_section_and_type_changing_sync(self, tmp_path: Path) -> None:
        """A nested [section.sub] key syncs via its dotted path and an int-to-string type change applies while keeping the inline comment."""
        source_path, target_path = write_pair(
            tmp_path,
            'count = "thirty"\n\n[outer.inner]\nflag = true\n',
            "count = 30  # inline note\n\n[outer.inner]\nflag = false\n",
        )

        result = sync_toml_values(source_path, target_path=target_path)

        assert target_path.read_text() == 'count = "thirty"  # inline note\n\n[outer.inner]\nflag = true\n'
        assert result.updated_keys == ["count", "outer.inner.flag"]
        assert [(change.key_path, change.old_value, change.new_value) for change in result.changes] == [
            ("count", 30, "thirty"),
            ("outer.inner.flag", False, True),
        ]

    def test_array_of_tables_synced_wholesale(self, tmp_path: Path) -> None:
        """An [[array-of-tables]] is one leaf, so a differing array is replaced wholesale by the source's."""
        source_path, target_path = write_pair(
            tmp_path,
            '[[servers]]\nname = "alpha"\nport = 9000\n',
            '[[servers]]\nname = "beta"\nport = 8000\n\n[[servers]]\nname = "gamma"\nport = 8001\n',
        )

        result = sync_toml_values(source_path, target_path=target_path)

        assert target_path.read_text() == '[[servers]]\nname = "alpha"\nport = 9000\n'
        assert result.updated_keys == ["servers"]

    @pytest.mark.parametrize("missing_file", ["source", "target"])
    def test_missing_file_raises_file_not_found(self, tmp_path: Path, missing_file: str) -> None:
        """There is no existence guard: a missing source or target raises a plain FileNotFoundError."""
        existing_path = tmp_path / "existing.toml"
        existing_path.write_text('key = "value"\n')
        absent_path = tmp_path / "absent.toml"

        if missing_file == "source":
            source_path, target_path = absent_path, existing_path
        else:
            source_path, target_path = existing_path, absent_path

        with pytest.raises(FileNotFoundError):
            sync_toml_values(source_path, target_path=target_path)
