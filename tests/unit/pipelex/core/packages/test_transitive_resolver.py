from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from semantic_version import Version  # type: ignore[import-untyped]

from pipelex.core.packages.dependency_resolver import (
    ResolvedDependency,
    resolve_all_dependencies,
)
from pipelex.core.packages.exceptions import TransitiveDependencyError
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency


def _make_manifest(
    address: str,
    version: str,
    dependencies: list[PackageDependency] | None = None,
) -> MthdsPackageManifest:
    """Helper to build a minimal manifest."""
    return MthdsPackageManifest(
        address=address,
        version=version,
        description=f"Test package {address}",
        dependencies=dependencies or [],
    )


def _make_resolved(
    alias: str,
    address: str,
    manifest: MthdsPackageManifest | None,
    tmp_path: Path,
) -> ResolvedDependency:
    """Helper to build a ResolvedDependency for mocking."""
    pkg_dir = tmp_path / alias
    pkg_dir.mkdir(exist_ok=True)
    return ResolvedDependency(
        alias=alias,
        address=address,
        manifest=manifest,
        package_root=pkg_dir,
        mthds_files=[],
        exported_pipe_codes=set(),
    )


class TestTransitiveResolver:
    """Unit tests for transitive dependency resolution with mocked VCS."""

    def test_linear_chain(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A->B->C: both B and C appear in results."""
        # B depends on C
        manifest_c = _make_manifest("github.com/org/pkg_c", "1.0.0")
        manifest_b = _make_manifest(
            "github.com/org/pkg_b",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_c", version="^1.0.0", alias="pkg_c"),
            ],
        )

        resolved_b = _make_resolved("pkg_b", "github.com/org/pkg_b", manifest_b, tmp_path)
        resolved_c = _make_resolved("pkg_c", "github.com/org/pkg_c", manifest_c, tmp_path)

        call_count = 0

        def mock_resolve_remote(dep: PackageDependency, **_kwargs: object) -> ResolvedDependency:
            nonlocal call_count
            call_count += 1
            if dep.address == "github.com/org/pkg_b":
                return resolved_b
            if dep.address == "github.com/org/pkg_c":
                return resolved_c
            msg = f"Unexpected address: {dep.address}"
            raise AssertionError(msg)

        mocker.patch(
            "pipelex.core.packages.dependency_resolver.resolve_remote_dependency",
            side_effect=mock_resolve_remote,
        )

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_b", version="^1.0.0", alias="pkg_b"),
            ],
        )

        result = resolve_all_dependencies(manifest_a, tmp_path)
        addresses = {dep.address for dep in result}
        assert "github.com/org/pkg_b" in addresses
        assert "github.com/org/pkg_c" in addresses
        assert call_count == 2

    def test_cycle_detection(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A->B->A: raises TransitiveDependencyError with 'cycle'."""
        # B depends on A (cycle)
        manifest_b = _make_manifest(
            "github.com/org/pkg_b",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_a", version="^1.0.0", alias="pkg_a"),
            ],
        )

        resolved_b = _make_resolved("pkg_b", "github.com/org/pkg_b", manifest_b, tmp_path)

        mocker.patch(
            "pipelex.core.packages.dependency_resolver.resolve_remote_dependency",
            return_value=resolved_b,
        )

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_b", version="^1.0.0", alias="pkg_b"),
            ],
        )

        with pytest.raises(TransitiveDependencyError, match="cycle"):
            resolve_all_dependencies(manifest_a, tmp_path)

    def test_diamond_resolved(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A->B, A->C, both depend on D: D resolved once with compatible version."""
        manifest_d = _make_manifest("github.com/org/pkg_d", "1.2.0")
        manifest_b = _make_manifest(
            "github.com/org/pkg_b",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^1.0.0", alias="pkg_d"),
            ],
        )
        manifest_c = _make_manifest(
            "github.com/org/pkg_c",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^1.1.0", alias="pkg_d"),
            ],
        )

        resolved_b = _make_resolved("pkg_b", "github.com/org/pkg_b", manifest_b, tmp_path)
        resolved_c = _make_resolved("pkg_c", "github.com/org/pkg_c", manifest_c, tmp_path)
        resolved_d = _make_resolved("pkg_d", "github.com/org/pkg_d", manifest_d, tmp_path)

        def mock_resolve_remote(dep: PackageDependency, **_kwargs: object) -> ResolvedDependency:
            if dep.address == "github.com/org/pkg_b":
                return resolved_b
            if dep.address == "github.com/org/pkg_c":
                return resolved_c
            if dep.address == "github.com/org/pkg_d":
                return resolved_d
            msg = f"Unexpected address: {dep.address}"
            raise AssertionError(msg)

        mocker.patch(
            "pipelex.core.packages.dependency_resolver.resolve_remote_dependency",
            side_effect=mock_resolve_remote,
        )

        # Mock version_satisfies to return True for compatible constraints
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.version_satisfies",
            return_value=True,
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_constraint",
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_version",
            return_value=Version("1.2.0"),
        )

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_b", version="^1.0.0", alias="pkg_b"),
                PackageDependency(address="github.com/org/pkg_c", version="^1.0.0", alias="pkg_c"),
            ],
        )

        result = resolve_all_dependencies(manifest_a, tmp_path)
        addresses = [dep.address for dep in result]
        # D should appear exactly once
        assert addresses.count("github.com/org/pkg_d") == 1
        # B and C should both be present
        assert "github.com/org/pkg_b" in addresses
        assert "github.com/org/pkg_c" in addresses

    def test_diamond_unsatisfiable(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """B needs D ^1.0.0, C needs D ^2.0.0: raises TransitiveDependencyError."""
        manifest_d_v1 = _make_manifest("github.com/org/pkg_d", "1.0.0")
        manifest_b = _make_manifest(
            "github.com/org/pkg_b",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^1.0.0", alias="pkg_d"),
            ],
        )
        manifest_c = _make_manifest(
            "github.com/org/pkg_c",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^2.0.0", alias="pkg_d"),
            ],
        )

        resolved_b = _make_resolved("pkg_b", "github.com/org/pkg_b", manifest_b, tmp_path)
        resolved_c = _make_resolved("pkg_c", "github.com/org/pkg_c", manifest_c, tmp_path)
        resolved_d = _make_resolved("pkg_d", "github.com/org/pkg_d", manifest_d_v1, tmp_path)

        def mock_resolve_remote(dep: PackageDependency, **_kwargs: object) -> ResolvedDependency:
            if dep.address == "github.com/org/pkg_b":
                return resolved_b
            if dep.address == "github.com/org/pkg_c":
                return resolved_c
            if dep.address == "github.com/org/pkg_d":
                return resolved_d
            msg = f"Unexpected address: {dep.address}"
            raise AssertionError(msg)

        mocker.patch(
            "pipelex.core.packages.dependency_resolver.resolve_remote_dependency",
            side_effect=mock_resolve_remote,
        )

        # Mock version_satisfies to return False (existing v1 doesn't satisfy ^2.0.0)
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.version_satisfies",
            return_value=False,
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_constraint",
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_version",
            return_value=Version("1.0.0"),
        )

        # Mock the tags listing for diamond resolution
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.list_remote_version_tags",
            return_value=[(Version("1.0.0"), "v1.0.0"), (Version("1.5.0"), "v1.5.0")],
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.select_minimum_version_for_multiple_constraints",
            return_value=None,  # no version satisfies both ^1.0.0 and ^2.0.0
        )

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_b", version="^1.0.0", alias="pkg_b"),
                PackageDependency(address="github.com/org/pkg_c", version="^1.0.0", alias="pkg_c"),
            ],
        )

        with pytest.raises(TransitiveDependencyError, match="No version"):
            resolve_all_dependencies(manifest_a, tmp_path)

    def test_local_deps_not_recursed(self, tmp_path: Path) -> None:
        """Local path dep's sub-deps are NOT resolved transitively."""
        # Create a local dep directory with a manifest that has dependencies
        local_dir = tmp_path / "local_pkg"
        local_dir.mkdir()
        methods_toml = """\
[package]
address = "github.com/org/local_pkg"
version = "1.0.0"
description = "Local package"

[dependencies]
sub_dep = { address = "github.com/org/sub_dep", version = "^1.0.0" }
"""
        (local_dir / "METHODS.toml").write_text(methods_toml)

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(
                    address="github.com/org/local_pkg",
                    version="1.0.0",
                    alias="local_pkg",
                    path=str(local_dir),
                ),
            ],
        )

        # If sub_dep were resolved, it would fail because there's no mock.
        # The fact it succeeds proves local deps are not recursed.
        result = resolve_all_dependencies(manifest_a, tmp_path)
        assert len(result) == 1
        assert result[0].alias == "local_pkg"

    def test_dedup_same_address(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Multiple paths to same address: resolved only once."""
        manifest_d = _make_manifest("github.com/org/pkg_d", "1.0.0")

        # Both B and C depend on D with the same constraint
        manifest_b = _make_manifest(
            "github.com/org/pkg_b",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^1.0.0", alias="pkg_d"),
            ],
        )
        manifest_c = _make_manifest(
            "github.com/org/pkg_c",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_d", version="^1.0.0", alias="pkg_d"),
            ],
        )

        resolved_b = _make_resolved("pkg_b", "github.com/org/pkg_b", manifest_b, tmp_path)
        resolved_c = _make_resolved("pkg_c", "github.com/org/pkg_c", manifest_c, tmp_path)
        resolved_d = _make_resolved("pkg_d", "github.com/org/pkg_d", manifest_d, tmp_path)

        resolve_count: dict[str, int] = {}

        def mock_resolve_remote(dep: PackageDependency, **_kwargs: object) -> ResolvedDependency:
            resolve_count[dep.address] = resolve_count.get(dep.address, 0) + 1
            if dep.address == "github.com/org/pkg_b":
                return resolved_b
            if dep.address == "github.com/org/pkg_c":
                return resolved_c
            if dep.address == "github.com/org/pkg_d":
                return resolved_d
            msg = f"Unexpected address: {dep.address}"
            raise AssertionError(msg)

        mocker.patch(
            "pipelex.core.packages.dependency_resolver.resolve_remote_dependency",
            side_effect=mock_resolve_remote,
        )

        # Mock version_satisfies for the dedup check
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.version_satisfies",
            return_value=True,
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_constraint",
            return_value=mocker.MagicMock(),
        )
        mocker.patch(
            "pipelex.core.packages.dependency_resolver.parse_version",
            return_value=Version("1.0.0"),
        )

        manifest_a = _make_manifest(
            "github.com/org/pkg_a",
            "1.0.0",
            dependencies=[
                PackageDependency(address="github.com/org/pkg_b", version="^1.0.0", alias="pkg_b"),
                PackageDependency(address="github.com/org/pkg_c", version="^1.0.0", alias="pkg_c"),
            ],
        )

        result = resolve_all_dependencies(manifest_a, tmp_path)
        addresses = [dep.address for dep in result]
        # D appears once (deduped)
        assert addresses.count("github.com/org/pkg_d") == 1
        # D was resolved only once via resolve_remote_dependency
        assert resolve_count.get("github.com/org/pkg_d", 0) == 1
