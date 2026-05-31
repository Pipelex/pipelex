"""Regression tests for remove_cursor_rules cleanup behavior."""

from pathlib import Path

from pipelex.kit.cursor_rules import remove_cursor_rules


class TestRemoveCursorRules:
    def test_removes_stale_pipelex_managed_file(self, tmp_path: Path):
        """A .mdc file with the `pipelex_managed: true` marker must be removed even when
        no corresponding source file exists under `pipelex/kit/agent_rules/` anymore.

        Regression test for the bug where removing a source file (e.g. `tdd.md`) would
        leave behind a stale `.cursor/rules/<name>.mdc` that the cleanup path could not
        discover because it only iterated currently-existing source files.
        """
        cursor_dir = tmp_path / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)

        stale_path = cursor_dir / "tdd.mdc"
        stale_path.write_text(
            "---\nalwaysApply: false\npipelex_managed: true\n---\n# TDD\n",
            encoding="utf-8",
        )
        user_path = cursor_dir / "user_custom.mdc"
        user_path.write_text("---\nalwaysApply: true\n---\n# my own rule\n", encoding="utf-8")

        remove_cursor_rules(tmp_path)

        assert not stale_path.exists(), "Stale Pipelex-managed .mdc must be deleted"
        assert user_path.exists(), "Unrelated user .mdc files must be preserved"

    def test_removes_current_source_file_without_marker(self, tmp_path: Path):
        """Files whose stem matches a currently-known agent_rules source must still be
        removed, even when they lack the `pipelex_managed` marker (backward compat for
        files generated before the marker existed).
        """
        cursor_dir = tmp_path / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)

        legacy_path = cursor_dir / "commands.mdc"
        legacy_path.write_text("---\nalwaysApply: true\n---\n# legacy\n", encoding="utf-8")

        remove_cursor_rules(tmp_path)

        assert not legacy_path.exists(), "Legacy unmarked .mdc matching a current source must still be deleted"

    def test_removes_legacy_tdd_mdc_without_marker(self, tmp_path: Path):
        """A pre-marker `tdd.mdc` whose source `tdd.md` has been removed from the kit
        must still be deleted via the declarative `deprecated_rule_stems` tombstone list.

        Migration regression test: existing Cursor users who ran sync before the
        `pipelex_managed` marker was introduced have stale `.cursor/rules/tdd.mdc` files.
        These have neither the marker nor a matching current source, so the only safe
        way to remove them is via an explicit deprecation list shipped with the kit.
        """
        cursor_dir = tmp_path / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)

        legacy_tdd = cursor_dir / "tdd.mdc"
        legacy_tdd.write_text(
            "---\nalwaysApply: false\ndescription: Test-Driven Development guide\n---\n# TDD\n",
            encoding="utf-8",
        )

        remove_cursor_rules(tmp_path)

        assert not legacy_tdd.exists(), "Legacy pre-marker tdd.mdc must be deleted via the deprecated stems list"
