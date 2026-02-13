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


# ============================================================
# Lock file TOML strings for lock file tests
# ============================================================

LOCK_FILE_TOML = """\
["github.com/pipelexlab/document-processing"]
version = "1.2.3"
hash = "sha256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
source = "https://github.com/pipelexlab/document-processing"

["github.com/pipelexlab/scoring-lib"]
version = "0.5.1"
hash = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
source = "https://github.com/pipelexlab/scoring-lib"
"""

EMPTY_LOCK_FILE_TOML = ""

INVALID_HASH_LOCK_FILE_TOML = """\
["github.com/pipelexlab/bad-hash"]
version = "1.0.0"
hash = "md5:not-a-valid-hash"
source = "https://github.com/pipelexlab/bad-hash"
"""
