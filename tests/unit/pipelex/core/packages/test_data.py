from typing import ClassVar

from pipelex.core.packages.manifest import DomainExports, MthdsPackageManifest, PackageDependency

# ============================================================
# TOML strings for parser tests
# ============================================================

FULL_MANIFEST_TOML = """\
[package]
address = "github.com/pipelexlab/legal-tools"
version = "1.0.0"
description = "Legal document analysis tools"
authors = ["PipelexLab"]
license = "MIT"
mthds_version = "0.5.0"

[dependencies]
scoring_lib = { address = "github.com/pipelexlab/scoring-lib", version = "2.0.0" }

[exports.legal.contracts]
pipes = ["extract_clause", "analyze_contract"]

[exports.scoring]
pipes = ["compute_weighted_score"]
"""

MINIMAL_MANIFEST_TOML = """\
[package]
address = "github.com/pipelexlab/minimal"
version = "0.1.0"
description = "A minimal MTHDS package"
"""

EMPTY_EXPORTS_DEPS_TOML = """\
[package]
address = "github.com/pipelexlab/empty"
version = "1.0.0"
description = "Package with empty exports and dependencies"

[dependencies]

[exports]
"""

MULTI_LEVEL_EXPORTS_TOML = """\
[package]
address = "github.com/pipelexlab/deep"
version = "1.0.0"
description = "Deep nested exports package"

[exports.legal.contracts.shareholder]
pipes = ["extract_shareholder_clause"]

[exports.legal.contracts]
pipes = ["extract_clause"]

[exports.scoring]
pipes = ["compute_score"]
"""

INVALID_TOML_SYNTAX = """\
[package
address = "broken
"""

MISSING_PACKAGE_SECTION_TOML = """\
[something_else]
foo = "bar"
"""

MISSING_REQUIRED_FIELDS_TOML = """\
[package]
description = "Missing address and version"
"""

NON_TABLE_DEPENDENCY_TOML = """\
[package]
address = "github.com/pipelexlab/bad-deps"
version = "1.0.0"
description = "Package with a non-table dependency entry"

[dependencies]
foo = "1.0.0"
"""

INVALID_DOMAIN_PATH_EXPORTS_TOML = """\
[package]
address = "github.com/pipelexlab/bad-exports"
version = "1.0.0"
description = "Package with an invalid domain path in exports"

[exports.InvalidDomain]
pipes = ["extract_clause"]
"""

INVALID_PIPE_NAME_EXPORTS_TOML = """\
[package]
address = "github.com/pipelexlab/bad-pipes"
version = "1.0.0"
description = "Package with an invalid pipe name in exports"

[exports.legal]
pipes = ["BadPipe"]
"""

# ============================================================
# Expected model instances
# ============================================================


class ManifestTestData:
    """Reusable expected manifest instances for test assertions."""

    FULL_MANIFEST: ClassVar[MthdsPackageManifest] = MthdsPackageManifest(
        address="github.com/pipelexlab/legal-tools",
        version="1.0.0",
        description="Legal document analysis tools",
        authors=["PipelexLab"],
        license="MIT",
        mthds_version="0.5.0",
        dependencies=[
            PackageDependency(
                address="github.com/pipelexlab/scoring-lib",
                version="2.0.0",
                alias="scoring_lib",
            ),
        ],
        exports=[
            DomainExports(domain_path="legal.contracts", pipes=["extract_clause", "analyze_contract"]),
            DomainExports(domain_path="scoring", pipes=["compute_weighted_score"]),
        ],
    )

    MINIMAL_MANIFEST: ClassVar[MthdsPackageManifest] = MthdsPackageManifest(
        address="github.com/pipelexlab/minimal",
        version="0.1.0",
        description="A minimal MTHDS package",
    )
