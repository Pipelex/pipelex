from pydantic import BaseModel, ConfigDict, Field

from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class PipeSignature(BaseModel):
    """Indexed representation of a pipe's typed signature.

    Stores pipe metadata and input/output concept specs as strings
    (blueprint-level, no runtime class loading).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipe_code: str
    pipe_type: str
    domain_code: str
    description: str
    input_specs: dict[str, str] = Field(default_factory=dict)
    output_spec: str
    is_exported: bool


class ConceptEntry(BaseModel):
    """Indexed representation of a concept definition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_code: str
    domain_code: str
    concept_ref: str
    description: str
    refines: str | None = None
    structure_fields: list[str] = Field(default_factory=list)


class DomainEntry(BaseModel):
    """Indexed representation of a domain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain_code: str
    description: str | None = None


class PackageIndexEntry(BaseModel):
    """Indexed view of a single package: metadata + domains + concepts + pipe signatures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    version: str
    description: str
    authors: list[str] = Field(default_factory=list)
    license: str | None = None
    domains: list[DomainEntry] = Field(default_factory=empty_list_factory_of(DomainEntry))
    concepts: list[ConceptEntry] = Field(default_factory=empty_list_factory_of(ConceptEntry))
    pipes: list[PipeSignature] = Field(default_factory=empty_list_factory_of(PipeSignature))
    dependencies: list[str] = Field(default_factory=list)


class PackageIndex(BaseModel):
    """Collection of indexed packages, keyed by address."""

    model_config = ConfigDict(extra="forbid")

    entries: dict[str, PackageIndexEntry] = Field(default_factory=dict)

    def add_entry(self, entry: PackageIndexEntry) -> None:
        """Add or replace a package index entry."""
        self.entries[entry.address] = entry

    def get_entry(self, address: str) -> PackageIndexEntry | None:
        """Retrieve an entry by address, or None if not found."""
        return self.entries.get(address)

    def remove_entry(self, address: str) -> bool:
        """Remove an entry by address. Returns True if it existed."""
        if address in self.entries:
            del self.entries[address]
            return True
        return False

    def all_concepts(self) -> list[tuple[str, ConceptEntry]]:
        """Return all concepts across all packages as (address, ConceptEntry) pairs."""
        result: list[tuple[str, ConceptEntry]] = []
        for address, entry in self.entries.items():
            for concept in entry.concepts:
                result.append((address, concept))
        return result

    def all_pipes(self) -> list[tuple[str, PipeSignature]]:
        """Return all pipes across all packages as (address, PipeSignature) pairs."""
        result: list[tuple[str, PipeSignature]] = []
        for address, entry in self.entries.items():
            for pipe in entry.pipes:
                result.append((address, pipe))
        return result
