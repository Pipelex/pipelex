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

# Address pattern: must contain at least one dot before a slash (hostname pattern)
# e.g. "github.com/org/repo", "example.io/pkg"
ADDRESS_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/[a-zA-Z0-9._/-]+$")


def is_valid_semver(version: str) -> bool:
    """Check if a version string is valid semver."""
    return SEMVER_PATTERN.match(version) is not None


def is_valid_address(address: str) -> bool:
    """Check if an address contains at least one dot before a slash (hostname pattern)."""
    return ADDRESS_PATTERN.match(address) is not None


class PackageDependency(BaseModel):
    """A dependency on another MTHDS package."""

    model_config = ConfigDict(extra="forbid")

    address: str
    version: str
    alias: str

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
    description: str | None = None
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
