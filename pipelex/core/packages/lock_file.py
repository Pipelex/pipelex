"""Lock file model, hash computation, TOML I/O, generation, and verification.

The lock file (``methods.lock``) records exact resolved versions and SHA-256
integrity hashes for remote dependencies, enabling reproducible builds.
"""

import hashlib
import re
from pathlib import Path
from typing import Any, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.packages.exceptions import IntegrityError, LockFileError
from pipelex.core.packages.manifest import MthdsPackageManifest, is_valid_semver
from pipelex.core.packages.package_cache import get_cached_package_path
from pipelex.tools.misc.toml_utils import TomlError, load_toml_from_content

LOCK_FILENAME = "methods.lock"
HASH_PREFIX = "sha256:"

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LockedPackage(BaseModel):
    """A single locked dependency entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    hash: str
    source: str

    @field_validator("version")
    @classmethod
    def validate_version(cls, version: str) -> str:
        if not is_valid_semver(version):
            msg = f"Invalid version '{version}' in lock file. Must be valid semver."
            raise ValueError(msg)
        return version

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, hash_value: str) -> str:
        if not _HASH_PATTERN.match(hash_value):
            msg = f"Invalid hash '{hash_value}'. Must be '{HASH_PREFIX}' followed by exactly 64 hex characters."
            raise ValueError(msg)
        return hash_value

    @field_validator("source")
    @classmethod
    def validate_source(cls, source: str) -> str:
        if not source.startswith("https://"):
            msg = f"Invalid source '{source}'. Must start with 'https://'."
            raise ValueError(msg)
        return source


class LockFile(BaseModel):
    """The methods.lock file model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    packages: dict[str, LockedPackage] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def compute_directory_hash(directory: Path) -> str:
    """Compute a deterministic SHA-256 hash of a directory's contents.

    Collects all regular files recursively, skips any path containing ``.git``
    in parts, sorts by POSIX-normalized relative path, and feeds each file's
    relative path string (UTF-8) + raw bytes into a single hasher.

    Args:
        directory: The directory to hash.

    Returns:
        A string in the form ``sha256:<64 hex chars>``.

    Raises:
        LockFileError: If the directory does not exist.
    """
    if not directory.is_dir():
        msg = f"Directory '{directory}' does not exist or is not a directory"
        raise LockFileError(msg)

    hasher = hashlib.sha256()

    # Collect all regular files, skip .git
    file_paths: list[Path] = []
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        if ".git" in file_path.relative_to(directory).parts:
            continue
        file_paths.append(file_path)

    # Sort by POSIX-normalized relative path for cross-platform determinism
    file_paths.sort(key=lambda path: path.relative_to(directory).as_posix())

    for file_path in file_paths:
        relative_posix = file_path.relative_to(directory).as_posix()
        hasher.update(relative_posix.encode("utf-8"))
        hasher.update(file_path.read_bytes())

    return f"{HASH_PREFIX}{hasher.hexdigest()}"


# ---------------------------------------------------------------------------
# TOML parse / serialize
# ---------------------------------------------------------------------------


def parse_lock_file(content: str) -> LockFile:
    """Parse a lock file TOML string into a ``LockFile`` model.

    Args:
        content: The raw TOML string.

    Returns:
        A validated ``LockFile``.

    Raises:
        LockFileError: If parsing or validation fails.
    """
    if not content.strip():
        return LockFile()

    try:
        raw = load_toml_from_content(content)
    except TomlError as exc:
        msg = f"Invalid TOML syntax in lock file: {exc.message}"
        raise LockFileError(msg) from exc

    packages: dict[str, LockedPackage] = {}
    for address, entry in raw.items():
        if not isinstance(entry, dict):
            msg = f"Lock file entry for '{address}' must be a table, got {type(entry).__name__}"
            raise LockFileError(msg)
        entry_dict = cast("dict[str, Any]", entry)
        try:
            packages[str(address)] = LockedPackage(**entry_dict)
        except Exception as exc:
            msg = f"Invalid lock file entry for '{address}': {exc}"
            raise LockFileError(msg) from exc

    return LockFile(packages=packages)


def serialize_lock_file(lock_file: LockFile) -> str:
    """Serialize a ``LockFile`` to a TOML string.

    Entries are sorted by address for deterministic output (clean VCS diffs).

    Args:
        lock_file: The lock file model to serialize.

    Returns:
        A TOML-formatted string.
    """
    doc = tomlkit.document()

    for address in sorted(lock_file.packages):
        locked = lock_file.packages[address]
        table = tomlkit.table()
        table.add("version", locked.version)
        table.add("hash", locked.hash)
        table.add("source", locked.source)
        doc.add(address, table)

    return tomlkit.dumps(doc)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Lock file generation
# ---------------------------------------------------------------------------


def generate_lock_file(
    manifest: MthdsPackageManifest,
    resolved_deps: list[Any],
) -> LockFile:
    """Generate a lock file from resolved dependencies.

    Locks all remote dependencies (including transitive) by using
    ``resolved.address`` directly. Local path overrides from the root
    manifest are excluded.

    Args:
        manifest: The consuming package's manifest.
        resolved_deps: List of ``ResolvedDependency`` from the resolver.

    Returns:
        A ``LockFile`` with entries for remote dependencies only.

    Raises:
        LockFileError: If a remote dependency has no manifest.
    """
    packages: dict[str, LockedPackage] = {}

    # Build set of local-override addresses from root manifest
    local_addresses = {dep.address for dep in manifest.dependencies if dep.path is not None}

    for resolved in resolved_deps:
        # Skip local path overrides
        if resolved.address in local_addresses:
            continue

        # Remote dep must have a manifest
        if resolved.manifest is None:
            msg = f"Remote dependency '{resolved.alias}' ({resolved.address}) has no manifest — cannot generate lock entry"
            raise LockFileError(msg)

        address = resolved.address
        version = resolved.manifest.version
        hash_value = compute_directory_hash(resolved.package_root)
        source = f"https://{address}"

        packages[address] = LockedPackage(
            version=version,
            hash=hash_value,
            source=source,
        )

    return LockFile(packages=packages)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_locked_package(
    locked: LockedPackage,
    address: str,
    cache_root: Path | None = None,
) -> None:
    """Verify a single locked package against its cached copy.

    Args:
        locked: The locked package entry.
        address: The package address.
        cache_root: Override for the cache root directory.

    Raises:
        IntegrityError: If the cached package is missing or its hash does not match.
    """
    # Extract version to locate cached dir
    cached_path = get_cached_package_path(address, locked.version, cache_root)

    if not cached_path.is_dir():
        msg = f"Cached package '{address}@{locked.version}' not found at '{cached_path}'"
        raise IntegrityError(msg)

    actual_hash = compute_directory_hash(cached_path)
    if actual_hash != locked.hash:
        msg = f"Integrity check failed for '{address}@{locked.version}': expected {locked.hash}, got {actual_hash}"
        raise IntegrityError(msg)


def verify_lock_file(
    lock_file: LockFile,
    cache_root: Path | None = None,
) -> None:
    """Verify all entries in a lock file against the cache.

    Args:
        lock_file: The lock file to verify.
        cache_root: Override for the cache root directory.

    Raises:
        IntegrityError: If any cached package is missing or has a hash mismatch.
    """
    for address, locked in lock_file.packages.items():
        verify_locked_package(locked, address, cache_root)
