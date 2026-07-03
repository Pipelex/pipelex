"""Unit tests for the pure glob-matching helpers of the drift engine (no git, no I/O)."""

from __future__ import annotations

from pipelex.cli.dev_cli.commands.drift.core import find_dead_patterns, match_files, match_pattern

TRACKED_FILES = [
    "CLAUDE.md",
    "docs/tools/cli/index.md",
    "docs/tools/cli/agent.md",
    "docs/configuration/config.md",
    "pipelex/pipelex.toml",
    "pipelex/cli/main.py",
    "pipelex/cli/agent_cli/CLAUDE.md",
    "pipelex/cli/dev_cli/commands/drift/core.py",
    "pipelex/system/configuration/configs.py",
    "pipelex/system/configuration/nested/deep.py",
]


class TestDriftCoreMatching:
    def test_exact_path_match(self) -> None:
        """A pattern without glob characters matches exactly one path."""
        assert match_pattern("pipelex/pipelex.toml", pattern="pipelex/pipelex.toml")
        assert not match_pattern("pipelex/pipelex2.toml", pattern="pipelex/pipelex.toml")

    def test_directory_prefix_with_trailing_slash(self) -> None:
        """A trailing-slash pattern matches every tracked file under the directory."""
        assert match_pattern("docs/tools/cli/index.md", pattern="docs/tools/cli/")
        assert match_pattern("docs/tools/cli/sub/page.md", pattern="docs/tools/cli/")
        assert not match_pattern("docs/tools/climate/index.md", pattern="docs/tools/cli/")

    def test_directory_prefix_without_trailing_slash(self) -> None:
        """Trailing slashes are normalized: with or without, the same files match."""
        assert match_pattern("docs/tools/cli/index.md", pattern="docs/tools/cli")
        assert not match_pattern("docs/tools/climate/index.md", pattern="docs/tools/cli")

    def test_single_star_does_not_cross_slash(self) -> None:
        """`*` matches within one path segment only."""
        assert match_pattern("pipelex/main.py", pattern="pipelex/*.py")
        assert not match_pattern("pipelex/cli/main.py", pattern="pipelex/*.py")

    def test_double_star_matches_zero_or_more_directories(self) -> None:
        """`**/` spans any number of directories, including none."""
        pattern = "pipelex/system/configuration/**/*.py"
        assert match_pattern("pipelex/system/configuration/configs.py", pattern=pattern)
        assert match_pattern("pipelex/system/configuration/nested/deep.py", pattern=pattern)
        assert not match_pattern("pipelex/system/other/configs.py", pattern=pattern)

    def test_trailing_double_star_matches_everything_under(self) -> None:
        """`dir/**` matches every file under dir, and nothing in sibling directories."""
        pattern = "pipelex/cli/dev_cli/**"
        assert match_pattern("pipelex/cli/dev_cli/commands/drift/core.py", pattern=pattern)
        assert not match_pattern("pipelex/cli/dev_cli2/foo.py", pattern=pattern)
        assert not match_pattern("pipelex/cli/main.py", pattern=pattern)

    def test_leading_double_star_matches_at_any_depth(self) -> None:
        """`**/NAME` matches the name at the repo root and at any depth."""
        assert match_pattern("CLAUDE.md", pattern="**/CLAUDE.md")
        assert match_pattern("pipelex/cli/agent_cli/CLAUDE.md", pattern="**/CLAUDE.md")
        assert not match_pattern("docs/tools/cli/index.md", pattern="**/CLAUDE.md")

    def test_question_mark_matches_single_non_slash_character(self) -> None:
        """`?` matches exactly one character within a segment."""
        assert match_pattern("docs/a.md", pattern="docs/?.md")
        assert not match_pattern("docs/ab.md", pattern="docs/?.md")
        assert not match_pattern("docs/a/b.md", pattern="docs/?.md")

    def test_matching_is_case_sensitive(self) -> None:
        """Matching is case-sensitive per POSIX."""
        assert not match_pattern("docs/tools/cli/index.md", pattern="Docs/**")
        assert not match_pattern("pipelex/pipelex.toml", pattern="PIPELEX/pipelex.toml")

    def test_match_files_applies_exclude_and_sorts(self) -> None:
        """match_files unions the trigger patterns, subtracts excludes, and returns sorted paths."""
        matched = match_files(
            TRACKED_FILES,
            patterns=["pipelex/cli/**/*.py"],
            exclude=["pipelex/cli/dev_cli/**"],
        )
        assert matched == ["pipelex/cli/main.py"]

    def test_match_files_multiple_patterns(self) -> None:
        matched = match_files(
            TRACKED_FILES,
            patterns=["pipelex/system/configuration/**/*.py", "pipelex/pipelex.toml"],
        )
        assert matched == [
            "pipelex/pipelex.toml",
            "pipelex/system/configuration/configs.py",
            "pipelex/system/configuration/nested/deep.py",
        ]

    def test_find_dead_patterns_reports_zero_match_patterns(self) -> None:
        """Patterns that match no tracked file are reported, in manifest order."""
        dead = find_dead_patterns(TRACKED_FILES, patterns=["nonexistent/**", "pipelex/pipelex.toml", "docs/missing.md"])
        assert dead == ["nonexistent/**", "docs/missing.md"]

    def test_find_dead_patterns_all_alive(self) -> None:
        dead = find_dead_patterns(TRACKED_FILES, patterns=["docs/tools/cli/", "**/CLAUDE.md"])
        assert dead == []
