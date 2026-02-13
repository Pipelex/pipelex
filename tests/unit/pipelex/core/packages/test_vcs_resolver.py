import pytest
from semantic_version import Version  # type: ignore[import-untyped]

from pipelex.core.packages.exceptions import VersionResolutionError
from pipelex.core.packages.vcs_resolver import address_to_clone_url, resolve_version_from_tags


class TestVCSResolver:
    """Unit tests for pure VCS resolver functions."""

    def test_address_to_clone_url_github(self):
        """Standard GitHub address maps to HTTPS clone URL."""
        result = address_to_clone_url("github.com/org/repo")
        assert result == "https://github.com/org/repo.git"

    def test_address_to_clone_url_generic_host(self):
        """Non-GitHub host address maps correctly."""
        result = address_to_clone_url("gitlab.example.io/team/project")
        assert result == "https://gitlab.example.io/team/project.git"

    def test_address_to_clone_url_already_dot_git(self):
        """Address already ending with .git does not get doubled."""
        result = address_to_clone_url("github.com/org/repo.git")
        assert result == "https://github.com/org/repo.git"
        assert not result.endswith(".git.git")

    def test_resolve_version_from_tags_selects_minimum(self):
        """MVS picks the lowest matching version."""
        tags: list[tuple[Version, str]] = [
            (Version("1.0.0"), "v1.0.0"),
            (Version("1.1.0"), "v1.1.0"),
            (Version("1.2.0"), "v1.2.0"),
            (Version("2.0.0"), "v2.0.0"),
        ]
        selected_version, selected_tag = resolve_version_from_tags(tags, "^1.0.0")
        assert selected_version == Version("1.0.0")
        assert selected_tag == "v1.0.0"

    def test_resolve_version_from_tags_no_match_raises(self):
        """No matching version raises VersionResolutionError."""
        tags: list[tuple[Version, str]] = [
            (Version("1.0.0"), "v1.0.0"),
            (Version("1.1.0"), "v1.1.0"),
        ]
        with pytest.raises(VersionResolutionError, match="No version satisfying"):
            resolve_version_from_tags(tags, "^2.0.0")

    def test_resolve_version_from_tags_empty_raises(self):
        """Empty tag list raises VersionResolutionError."""
        with pytest.raises(VersionResolutionError, match="No version tags available"):
            resolve_version_from_tags([], "^1.0.0")
