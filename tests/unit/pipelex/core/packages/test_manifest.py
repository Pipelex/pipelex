import pytest
from pydantic import ValidationError

from pipelex.core.packages.manifest import DomainExports, MthdsPackageManifest, PackageDependency


class TestMthdsPackageManifest:
    """Tests for manifest model validation."""

    def test_valid_full_manifest(self):
        """Valid manifest with all fields populated."""
        manifest = MthdsPackageManifest(
            address="github.com/pipelexlab/legal-tools",
            version="1.0.0",
            description="Legal analysis",
            authors=["Alice", "Bob"],
            license="MIT",
            mthds_version="0.5.0",
            dependencies=[
                PackageDependency(address="github.com/org/dep", version="2.0.0", alias="my_dep"),
            ],
            exports=[
                DomainExports(domain_path="legal.contracts", pipes=["extract_clause"]),
            ],
        )
        assert manifest.address == "github.com/pipelexlab/legal-tools"
        assert manifest.version == "1.0.0"
        assert len(manifest.dependencies) == 1
        assert manifest.dependencies[0].alias == "my_dep"
        assert len(manifest.exports) == 1
        assert manifest.exports[0].domain_path == "legal.contracts"

    def test_valid_minimal_manifest(self):
        """Minimal manifest with only required fields."""
        manifest = MthdsPackageManifest(
            address="github.com/org/pkg",
            version="0.1.0",
            description="Minimal test package",
        )
        assert manifest.address == "github.com/org/pkg"
        assert manifest.version == "0.1.0"
        assert manifest.description == "Minimal test package"
        assert manifest.authors == []
        assert manifest.dependencies == []
        assert manifest.exports == []

    def test_missing_description_fails(self):
        """Missing description should fail validation."""
        with pytest.raises(ValidationError):
            MthdsPackageManifest(
                address="github.com/org/repo",
                version="1.0.0",
            )  # type: ignore[call-arg]

    def test_empty_description_fails(self):
        """Empty description should fail validation."""
        with pytest.raises(ValidationError, match="must not be empty"):
            MthdsPackageManifest(
                address="github.com/org/repo",
                version="1.0.0",
                description="   ",
            )

    def test_invalid_address_no_hostname(self):
        """Address without hostname pattern should fail."""
        with pytest.raises(ValidationError, match="Invalid package address"):
            MthdsPackageManifest(
                address="no-dots-or-slashes",
                version="1.0.0",
                description="Test",
            )

    def test_invalid_address_no_slash(self):
        """Address with dots but no slash should fail."""
        with pytest.raises(ValidationError, match="Invalid package address"):
            MthdsPackageManifest(
                address="github.com",
                version="1.0.0",
                description="Test",
            )

    def test_invalid_version_not_semver(self):
        """Non-semver version should fail."""
        with pytest.raises(ValidationError, match="Invalid version"):
            MthdsPackageManifest(
                address="github.com/org/repo",
                version="not-a-version",
                description="Test",
            )

    def test_invalid_version_partial(self):
        """Partial semver should fail."""
        with pytest.raises(ValidationError, match="Invalid version"):
            MthdsPackageManifest(
                address="github.com/org/repo",
                version="1.0",
                description="Test",
            )

    def test_valid_semver_with_prerelease(self):
        """Semver with prerelease tag should pass."""
        manifest = MthdsPackageManifest(
            address="github.com/org/repo",
            version="1.0.0-beta.1",
            description="Test",
        )
        assert manifest.version == "1.0.0-beta.1"

    def test_duplicate_dependency_aliases(self):
        """Duplicate aliases should fail validation."""
        with pytest.raises(ValidationError, match="Duplicate dependency alias"):
            MthdsPackageManifest(
                address="github.com/org/repo",
                version="1.0.0",
                description="Test",
                dependencies=[
                    PackageDependency(address="github.com/org/dep1", version="1.0.0", alias="same_alias"),
                    PackageDependency(address="github.com/org/dep2", version="2.0.0", alias="same_alias"),
                ],
            )

    def test_invalid_dependency_alias_not_snake_case(self):
        """Dependency alias that is not snake_case should fail."""
        with pytest.raises(ValidationError, match="Invalid dependency alias"):
            PackageDependency(
                address="github.com/org/dep",
                version="1.0.0",
                alias="NotSnakeCase",
            )

    @pytest.mark.parametrize(
        "reserved_domain",
        ["native", "mthds", "pipelex"],
    )
    def test_reserved_domain_exact_in_exports_rejected(self, reserved_domain: str):
        """Exact reserved domain names in exports should be rejected."""
        with pytest.raises(ValidationError, match="reserved domain"):
            DomainExports(
                domain_path=reserved_domain,
                pipes=["some_pipe"],
            )

    @pytest.mark.parametrize(
        "reserved_domain_path",
        ["native.concepts", "mthds.core", "pipelex.internal"],
    )
    def test_reserved_domain_prefix_in_exports_rejected(self, reserved_domain_path: str):
        """Hierarchical paths starting with a reserved domain should be rejected."""
        with pytest.raises(ValidationError, match="reserved domain"):
            DomainExports(
                domain_path=reserved_domain_path,
                pipes=["some_pipe"],
            )

    @pytest.mark.parametrize(
        "safe_domain",
        ["legal", "my_native_utils", "pipeline", "scoring"],
    )
    def test_non_reserved_domain_accepted(self, safe_domain: str):
        """Domain names that are not reserved should pass validation."""
        export = DomainExports(
            domain_path=safe_domain,
            pipes=["some_pipe"],
        )
        assert export.domain_path == safe_domain

    def test_invalid_domain_path_in_exports(self):
        """Invalid domain path in exports should fail."""
        with pytest.raises(ValidationError, match="Invalid domain path"):
            DomainExports(
                domain_path="InvalidDomain",
                pipes=["my_pipe"],
            )

    def test_invalid_pipe_name_in_exports(self):
        """Invalid pipe name in exports should fail."""
        with pytest.raises(ValidationError, match="Invalid pipe name"):
            DomainExports(
                domain_path="valid_domain",
                pipes=["InvalidPipeName"],
            )

    def test_valid_hierarchical_domain_in_exports(self):
        """Hierarchical domain path in exports should pass."""
        export = DomainExports(
            domain_path="legal.contracts.shareholder",
            pipes=["extract_clause"],
        )
        assert export.domain_path == "legal.contracts.shareholder"

    def test_empty_dependencies_and_exports(self):
        """Empty lists for dependencies and exports should pass."""
        manifest = MthdsPackageManifest(
            address="github.com/org/repo",
            version="1.0.0",
            description="Test",
            dependencies=[],
            exports=[],
        )
        assert manifest.dependencies == []
        assert manifest.exports == []

    @pytest.mark.parametrize(
        "version_str",
        [
            "^1.0.0",
            "~1.0.0",
            ">=1.0.0",
            "<=2.0.0",
            ">1.0.0",
            "<2.0.0",
            "==1.0.0",
            "!=1.0.0",
            ">=1.0.0, <2.0.0",
            "*",
            "1.*",
            "1.0.*",
            "1.0.0",
            "2.1.3-beta.1",
        ],
    )
    def test_valid_dependency_version_constraints(self, version_str: str):
        """Version constraints using Poetry/uv range syntax should pass."""
        dep = PackageDependency(
            address="github.com/org/dep",
            version=version_str,
            alias="my_dep",
        )
        assert dep.version == version_str

    @pytest.mark.parametrize(
        "version_str",
        [
            "not-a-version",
            "abc",
            "1.0.0.0",
            ">>1.0.0",
            "~=1.0.0",
        ],
    )
    def test_invalid_dependency_version_constraints(self, version_str: str):
        """Invalid version constraint strings should fail."""
        with pytest.raises(ValidationError, match="Invalid version constraint"):
            PackageDependency(
                address="github.com/org/dep",
                version=version_str,
                alias="my_dep",
            )
