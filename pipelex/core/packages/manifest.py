import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.domains.validation import is_domain_code_valid
from pipelex.core.pipes.validation import is_pipe_code_valid
from pipelex.tools.misc.string_utils import is_snake_case
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pipelex.types import Self

# Semver regex: MAJOR.MINOR.PATCH with optional pre-release and build metadata
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Version constraint pattern: supports standard range syntax used by Poetry/uv.
# A single constraint is: optional operator + semver (with optional wildcard minor/patch).
# Multiple constraints can be comma-separated (e.g., ">=1.0.0, <2.0.0").
# Supported forms: "1.0.0", "^1.0.0", "~1.0.0", ">=1.0.0", "<=1.0.0", ">1.0.0", "<1.0.0",
# "==1.0.0", "!=1.0.0", ">=1.0.0, <2.0.0", "*", "1.*", "1.0.*"
_SINGLE_CONSTRAINT = (
    r"(?:"
    r"\*"  # wildcard: *
    r"|(?:(?:\^|~|>=?|<=?|==|!=)?(?:0|[1-9]\d*)(?:\.(?:0|[1-9]\d*|\*))?(?:\.(?:0|[1-9]\d*|\*))?)"  # [op]MAJOR[.MINOR[.PATCH]]
    r"(?:-(?:(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?)"  # optional prerelease
)
VERSION_CONSTRAINT_PATTERN = re.compile(rf"^{_SINGLE_CONSTRAINT}(?:\s*,\s*{_SINGLE_CONSTRAINT})*$")

# Address pattern: must contain at least one dot before a slash (hostname pattern)
# e.g. "github.com/org/repo", "example.io/pkg"
ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+$")

RESERVED_DOMAINS: frozenset[str] = frozenset({"native", "mthds", "pipelex"})


def is_reserved_domain_path(domain_path: str) -> bool:
    """Check if a domain path starts with a reserved domain segment."""
    first_segment = domain_path.split(".", maxsplit=1)[0]
    return first_segment in RESERVED_DOMAINS


def is_valid_semver(version: str) -> bool:
    """Check if a version string is valid semver."""
    return SEMVER_PATTERN.match(version) is not None


def is_valid_version_constraint(constraint: str) -> bool:
    """Check if a version constraint string is valid.

    Supports standard range syntax used by Poetry/uv:
    - Exact: "1.0.0"
    - Caret: "^1.0.0" (compatible release)
    - Tilde: "~1.0.0" (approximately compatible)
    - Comparison: ">=1.0.0", "<=1.0.0", ">1.0.0", "<1.0.0", "==1.0.0", "!=1.0.0"
    - Compound: ">=1.0.0, <2.0.0"
    - Wildcard: "*", "1.*", "1.0.*"
    """
    return VERSION_CONSTRAINT_PATTERN.match(constraint.strip()) is not None


def is_valid_address(address: str) -> bool:
    """Check if an address contains at least one dot before a slash (hostname pattern)."""
    return ADDRESS_PATTERN.match(address) is not None


class PackageDependency(BaseModel):
    """A dependency on another MTHDS package."""

    model_config = ConfigDict(extra="forbid")

    address: str
    version: str
    alias: str
    path: str | None = None

    @field_validator("address")
    @classmethod
    def validate_address(cls, address: str) -> str:
        if not is_valid_address(address):
            msg = f"Invalid package address '{address}'. Address must follow hostname/path pattern (e.g. 'github.com/org/repo')."
            raise ValueError(msg)
        return address

    @field_validator("version")
    @classmethod
    def validate_version(cls, version: str) -> str:
        if not is_valid_version_constraint(version):
            msg = f"Invalid version constraint '{version}'. Must be a valid version range (e.g. '1.0.0', '^1.0.0', '>=1.0.0, <2.0.0')."
            raise ValueError(msg)
        return version

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, alias: str) -> str:
        if not is_snake_case(alias):
            msg = f"Invalid dependency alias '{alias}'. Must be snake_case."
            raise ValueError(msg)
        return alias


class DomainExports(BaseModel):
    """Exports for a single domain within a package."""

    model_config = ConfigDict(extra="forbid")

    domain_path: str
    pipes: list[str] = Field(default_factory=list)

    @field_validator("domain_path")
    @classmethod
    def validate_domain_path(cls, domain_path: str) -> str:
        if not is_domain_code_valid(domain_path):
            msg = f"Invalid domain path '{domain_path}' in [exports]. Domain paths must be dot-separated snake_case segments."
            raise ValueError(msg)
        if is_reserved_domain_path(domain_path):
            first_segment = domain_path.split(".", maxsplit=1)[0]
            msg = (
                f"Domain path '{domain_path}' uses reserved domain '{first_segment}'. "
                f"Reserved domains ({', '.join(sorted(RESERVED_DOMAINS))}) cannot be used in package exports."
            )
            raise ValueError(msg)
        return domain_path

    @field_validator("pipes")
    @classmethod
    def validate_pipes(cls, pipes: list[str]) -> list[str]:
        for pipe_name in pipes:
            if not is_pipe_code_valid(pipe_name):
                msg = f"Invalid pipe name '{pipe_name}' in [exports]. Pipe names must be in snake_case."
                raise ValueError(msg)
        return pipes


class MthdsPackageManifest(BaseModel):
    """The METHODS.toml package manifest model."""

    model_config = ConfigDict(extra="forbid")

    address: str
    version: str
    description: str
    authors: list[str] = Field(default_factory=list)
    license: str | None = None
    mthds_version: str | None = None

    dependencies: list[PackageDependency] = Field(default_factory=empty_list_factory_of(PackageDependency))
    exports: list[DomainExports] = Field(default_factory=empty_list_factory_of(DomainExports))

    @field_validator("address")
    @classmethod
    def validate_address(cls, address: str) -> str:
        if not is_valid_address(address):
            msg = f"Invalid package address '{address}'. Address must follow hostname/path pattern (e.g. 'github.com/org/repo')."
            raise ValueError(msg)
        return address

    @field_validator("version")
    @classmethod
    def validate_version(cls, version: str) -> str:
        if not is_valid_semver(version):
            msg = f"Invalid version '{version}'. Must be valid semver (e.g. '1.0.0', '2.1.3-beta.1')."
            raise ValueError(msg)
        return version

    @field_validator("description")
    @classmethod
    def validate_description(cls, description: str) -> str:
        if not description.strip():
            msg = "Package description must not be empty."
            raise ValueError(msg)
        return description

    @model_validator(mode="after")
    def validate_unique_dependency_aliases(self) -> Self:
        """Ensure all dependency aliases are unique."""
        seen_aliases: set[str] = set()
        for dep in self.dependencies:
            if dep.alias in seen_aliases:
                msg = f"Duplicate dependency alias '{dep.alias}'. Each dependency must have a unique alias."
                raise ValueError(msg)
            seen_aliases.add(dep.alias)
        return self
