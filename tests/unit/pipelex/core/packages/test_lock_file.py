from pathlib import Path

import pytest
from pydantic import ValidationError

from pipelex.core.packages.dependency_resolver import ResolvedDependency
from pipelex.core.packages.exceptions import IntegrityError, LockFileError
from pipelex.core.packages.lock_file import (
    LockedPackage,
    LockFile,
    compute_directory_hash,
    generate_lock_file,
    parse_lock_file,
    serialize_lock_file,
    verify_locked_package,
)
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency
from pipelex.core.packages.package_cache import store_in_cache
from tests.unit.pipelex.core.packages.test_data import (
    EMPTY_LOCK_FILE_TOML,
    INVALID_HASH_LOCK_FILE_TOML,
    LOCK_FILE_TOML,
)


class TestLockFile:
    """Tests for lock file models, parsing, serialization, hashing, and verification."""

    # ----------------------------------------------------------------
    # Parsing
    # ----------------------------------------------------------------

    def test_parse_lock_file(self):
        """Parse a 2-entry TOML, assert addresses/versions/hashes/sources."""
        lock = parse_lock_file(LOCK_FILE_TOML)
        assert len(lock.packages) == 2

        doc_pkg = lock.packages["github.com/pipelexlab/document-processing"]
        assert doc_pkg.version == "1.2.3"
        assert doc_pkg.hash == "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert doc_pkg.source == "https://github.com/pipelexlab/document-processing"

        scoring_pkg = lock.packages["github.com/pipelexlab/scoring-lib"]
        assert scoring_pkg.version == "0.5.1"
        assert scoring_pkg.hash == "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        assert scoring_pkg.source == "https://github.com/pipelexlab/scoring-lib"

    def test_parse_empty_lock_file(self):
        """Empty content produces an empty LockFile."""
        lock = parse_lock_file(EMPTY_LOCK_FILE_TOML)
        assert lock.packages == {}

    def test_parse_invalid_toml_raises(self):
        """Bad TOML syntax raises LockFileError."""
        with pytest.raises(LockFileError, match="Invalid TOML syntax"):
            parse_lock_file('[broken\nversion = "oops"')

    def test_parse_invalid_hash_raises(self):
        """Wrong hash prefix raises LockFileError."""
        with pytest.raises(LockFileError, match="Invalid lock file entry"):
            parse_lock_file(INVALID_HASH_LOCK_FILE_TOML)

    # ----------------------------------------------------------------
    # Serialization
    # ----------------------------------------------------------------

    def test_serialize_lock_file(self):
        """Serialize a model and assert TOML structure."""
        lock = LockFile(
            packages={
                "github.com/org/repo": LockedPackage(
                    version="1.0.0",
                    hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    source="https://github.com/org/repo",
                ),
            }
        )
        toml_str = serialize_lock_file(lock)
        assert '["github.com/org/repo"]' in toml_str
        assert 'version = "1.0.0"' in toml_str
        assert "sha256:aaa" in toml_str
        assert 'source = "https://github.com/org/repo"' in toml_str

    def test_serialize_roundtrip(self):
        """Parse -> serialize -> parse yields the same model."""
        original = parse_lock_file(LOCK_FILE_TOML)
        toml_str = serialize_lock_file(original)
        roundtripped = parse_lock_file(toml_str)
        assert roundtripped.packages.keys() == original.packages.keys()
        for address in original.packages:
            assert roundtripped.packages[address].version == original.packages[address].version
            assert roundtripped.packages[address].hash == original.packages[address].hash
            assert roundtripped.packages[address].source == original.packages[address].source

    def test_serialize_deterministic_order(self):
        """Entries are sorted by address regardless of insertion order."""
        lock = LockFile(
            packages={
                "github.com/zzz/last": LockedPackage(
                    version="2.0.0",
                    hash="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    source="https://github.com/zzz/last",
                ),
                "github.com/aaa/first": LockedPackage(
                    version="1.0.0",
                    hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    source="https://github.com/aaa/first",
                ),
            }
        )
        toml_str = serialize_lock_file(lock)
        aaa_pos = toml_str.index("aaa/first")
        zzz_pos = toml_str.index("zzz/last")
        assert aaa_pos < zzz_pos

    # ----------------------------------------------------------------
    # Hash computation
    # ----------------------------------------------------------------

    def test_compute_directory_hash_deterministic(self, tmp_path: Path):
        """Same directory hashed twice yields the same result."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "file.txt").write_text("hello")
        hash_one = compute_directory_hash(pkg_dir)
        hash_two = compute_directory_hash(pkg_dir)
        assert hash_one == hash_two
        assert hash_one.startswith("sha256:")
        assert len(hash_one) == len("sha256:") + 64

    def test_compute_directory_hash_content_sensitive(self, tmp_path: Path):
        """Changed content produces a different hash."""
        dir_a = tmp_path / "dir_a"
        dir_a.mkdir()
        (dir_a / "file.txt").write_text("content A")

        dir_b = tmp_path / "dir_b"
        dir_b.mkdir()
        (dir_b / "file.txt").write_text("content B")

        assert compute_directory_hash(dir_a) != compute_directory_hash(dir_b)

    def test_compute_directory_hash_path_sensitive(self, tmp_path: Path):
        """Same content but different filename produces a different hash."""
        dir_a = tmp_path / "dir_a"
        dir_a.mkdir()
        (dir_a / "alpha.txt").write_text("same")

        dir_b = tmp_path / "dir_b"
        dir_b.mkdir()
        (dir_b / "beta.txt").write_text("same")

        assert compute_directory_hash(dir_a) != compute_directory_hash(dir_b)

    def test_compute_directory_hash_skips_git_dir(self, tmp_path: Path):
        """Files inside .git/ are excluded from the hash."""
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "file.txt").write_text("hello")

        hash_without_git = compute_directory_hash(pkg_dir)

        # Add .git/ contents
        git_dir = pkg_dir / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "config").write_text("[core]\n")

        hash_with_git = compute_directory_hash(pkg_dir)
        assert hash_without_git == hash_with_git

    def test_compute_directory_hash_nonexistent_raises(self, tmp_path: Path):
        """Non-existent directory raises LockFileError."""
        with pytest.raises(LockFileError, match="does not exist"):
            compute_directory_hash(tmp_path / "nonexistent")

    # ----------------------------------------------------------------
    # Verification
    # ----------------------------------------------------------------

    def test_verify_locked_package_success(self, tmp_path: Path):
        """Build + verify matching hash passes without error."""
        cache_root = tmp_path / "cache"
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "METHODS.toml").write_text("[package]\n")
        (source_dir / "data.mthds").write_text("bundle content\n")

        address = "github.com/org/repo"
        version = "1.0.0"
        cached_path = store_in_cache(source_dir, address, version, cache_root=cache_root)

        expected_hash = compute_directory_hash(cached_path)
        locked = LockedPackage(
            version=version,
            hash=expected_hash,
            source=f"https://{address}",
        )

        # Should not raise
        verify_locked_package(locked, address, cache_root=cache_root)

    def test_verify_locked_package_mismatch(self, tmp_path: Path):
        """Modified content raises IntegrityError."""
        cache_root = tmp_path / "cache"
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "METHODS.toml").write_text("[package]\n")

        address = "github.com/org/repo"
        version = "1.0.0"
        cached_path = store_in_cache(source_dir, address, version, cache_root=cache_root)

        # Record a fake hash
        locked = LockedPackage(
            version=version,
            hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
            source=f"https://{address}",
        )

        # Cached content doesn't match the fake hash
        assert compute_directory_hash(cached_path) != locked.hash
        with pytest.raises(IntegrityError, match="Integrity check failed"):
            verify_locked_package(locked, address, cache_root=cache_root)

    def test_verify_locked_package_not_cached(self, tmp_path: Path):
        """Missing cache directory raises IntegrityError."""
        locked = LockedPackage(
            version="1.0.0",
            hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            source="https://github.com/org/missing",
        )
        with pytest.raises(IntegrityError, match="not found"):
            verify_locked_package(locked, "github.com/org/missing", cache_root=tmp_path)

    # ----------------------------------------------------------------
    # Lock file generation
    # ----------------------------------------------------------------

    def test_generate_lock_file_remote_only(self, tmp_path: Path):
        """1 local + 1 remote dep: only the remote appears in the lock file."""
        # Set up a cached remote package
        remote_dir = tmp_path / "remote_src"
        remote_dir.mkdir()
        (remote_dir / "METHODS.toml").write_text("[package]\n")
        (remote_dir / "main.mthds").write_text("content\n")

        manifest = MthdsPackageManifest(
            address="github.com/org/consumer",
            version="1.0.0",
            description="Consumer package",
            dependencies=[
                PackageDependency(
                    alias="local_dep",
                    address="github.com/org/local",
                    version="1.0.0",
                    path="../local",
                ),
                PackageDependency(
                    alias="remote_dep",
                    address="github.com/org/remote",
                    version="2.0.0",
                ),
            ],
        )

        remote_manifest = MthdsPackageManifest(
            address="github.com/org/remote",
            version="2.0.0",
            description="Remote package",
        )

        resolved_deps = [
            ResolvedDependency(
                alias="local_dep",
                manifest=None,
                package_root=tmp_path / "local",
                mthds_files=[],
                exported_pipe_codes=set(),
            ),
            ResolvedDependency(
                alias="remote_dep",
                manifest=remote_manifest,
                package_root=remote_dir,
                mthds_files=[],
                exported_pipe_codes=set(),
            ),
        ]

        lock = generate_lock_file(manifest, resolved_deps)

        assert len(lock.packages) == 1
        assert "github.com/org/remote" in lock.packages
        assert lock.packages["github.com/org/remote"].version == "2.0.0"
        assert lock.packages["github.com/org/remote"].source == "https://github.com/org/remote"
        assert lock.packages["github.com/org/remote"].hash.startswith("sha256:")

    def test_generate_lock_file_empty_no_remote(self, tmp_path: Path):
        """Only local deps produce an empty lock file."""
        manifest = MthdsPackageManifest(
            address="github.com/org/consumer",
            version="1.0.0",
            description="Consumer with only local deps",
            dependencies=[
                PackageDependency(
                    alias="local_only",
                    address="github.com/org/local",
                    version="1.0.0",
                    path="../local",
                ),
            ],
        )

        local_dir = tmp_path / "local"
        local_dir.mkdir()

        resolved_deps = [
            ResolvedDependency(
                alias="local_only",
                manifest=None,
                package_root=local_dir,
                mthds_files=[],
                exported_pipe_codes=set(),
            ),
        ]

        lock = generate_lock_file(manifest, resolved_deps)
        assert lock.packages == {}

    # ----------------------------------------------------------------
    # Model frozen
    # ----------------------------------------------------------------

    def test_locked_package_model_frozen(self):
        """Mutation attempt raises an error on the frozen model."""
        locked = LockedPackage(
            version="1.0.0",
            hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            source="https://github.com/org/repo",
        )
        with pytest.raises(ValidationError):
            locked.version = "2.0.0"  # type: ignore[misc]
