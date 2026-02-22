from pathlib import Path

from pipelex.core.packages.package_cache import (
    get_cached_package_path,
    is_cached,
    remove_cached_package,
    store_in_cache,
)


class TestPackageCache:
    """Unit tests for package cache operations using tmp_path."""

    def test_get_cached_package_path_structure(self, tmp_path: Path):
        """Cache path follows {root}/{address}/{version}/ layout."""
        result = get_cached_package_path("github.com/org/repo", "1.0.0", cache_root=tmp_path)
        assert result == tmp_path / "github.com/org/repo" / "1.0.0"

    def test_is_cached_false_when_empty(self, tmp_path: Path):
        """Cache miss when directory does not exist."""
        assert is_cached("github.com/org/repo", "1.0.0", cache_root=tmp_path) is False

    def test_store_and_is_cached(self, tmp_path: Path):
        """Round-trip: store then lookup returns True."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "METHODS.toml").write_text("[package]\n")

        result = store_in_cache(source_dir, "github.com/org/repo", "1.0.0", cache_root=tmp_path)

        assert result.is_dir()
        assert is_cached("github.com/org/repo", "1.0.0", cache_root=tmp_path) is True

    def test_store_removes_dot_git(self, tmp_path: Path):
        """.git/ directory is not present in the cached copy."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "METHODS.toml").write_text("[package]\n")
        git_dir = source_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        result = store_in_cache(source_dir, "github.com/org/repo", "1.0.0", cache_root=tmp_path)

        assert not (result / ".git").exists()

    def test_store_preserves_package_content(self, tmp_path: Path):
        """METHODS.toml and .mthds subdirectory content survive caching."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "METHODS.toml").write_text("[package]\naddress = 'test'\n")
        mthds_dir = source_dir / ".mthds"
        mthds_dir.mkdir()
        (mthds_dir / "main.mthds").write_text("bundle content\n")

        result = store_in_cache(source_dir, "github.com/org/repo", "1.0.0", cache_root=tmp_path)

        assert (result / "METHODS.toml").is_file()
        assert (result / ".mthds" / "main.mthds").is_file()
        assert (result / "METHODS.toml").read_text() == "[package]\naddress = 'test'\n"

    def test_remove_cached_package(self, tmp_path: Path):
        """Removing a cached package returns True and deletes the directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "data.txt").write_text("content")

        store_in_cache(source_dir, "github.com/org/repo", "1.0.0", cache_root=tmp_path)
        assert is_cached("github.com/org/repo", "1.0.0", cache_root=tmp_path) is True

        removed = remove_cached_package("github.com/org/repo", "1.0.0", cache_root=tmp_path)
        assert removed is True
        assert is_cached("github.com/org/repo", "1.0.0", cache_root=tmp_path) is False

    def test_remove_not_cached_returns_false(self, tmp_path: Path):
        """Removing a non-existent cache entry returns False."""
        removed = remove_cached_package("github.com/org/missing", "9.9.9", cache_root=tmp_path)
        assert removed is False
