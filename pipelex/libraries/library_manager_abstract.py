from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_library_abstract import ConceptLibraryAbstract
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_library_abstract import DomainLibraryAbstract
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_library_abstract import PipeLibraryAbstract

if TYPE_CHECKING:
    from pipelex.libraries.library import Library


class LibraryManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def open_library(self, library_id: str) -> None:
        """Open a new library with the given library_id."""
        pass

    @abstractmethod
    def close_library(self, library_id: str) -> None:
        """Close and cleanup a library with the given library_id."""
        pass

    @abstractmethod
    def get_library(self, library_id: str | None = None) -> "Library":
        """Get the Library object for a specific library_id."""
        pass

    @abstractmethod
    def get_domain_library(self, library_id: str | None = None) -> DomainLibraryAbstract:
        """Get the domain library for a specific library_id."""
        pass

    @abstractmethod
    def get_concept_library(self, library_id: str | None = None) -> ConceptLibraryAbstract:
        """Get the concept library for a specific library_id."""
        pass

    @abstractmethod
    def get_pipe_library(self, library_id: str | None = None) -> PipeLibraryAbstract:
        """Get the pipe library for a specific library_id."""
        pass

    @abstractmethod
    def get_required_domain(self, domain: str, library_id: str | None = None) -> Domain:
        """Get a required domain from the specified library."""
        pass

    @abstractmethod
    def get_required_concept(self, concept_string: str, library_id: str | None = None) -> Concept:
        """Get a required concept from the specified library."""
        pass

    @abstractmethod
    def get_required_pipe(self, pipe_code: str, library_id: str | None = None) -> PipeAbstract:
        """Get a required pipe from the specified library."""
        pass

    @abstractmethod
    def validate_libraries(self, library_id: str | None = None) -> None:
        pass

    @abstractmethod
    def load_libraries(
        self,
        library_id: str | None = None,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint, library_id: str | None = None) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def remove_from_blueprint(self, blueprint: PipelexBundleBlueprint, library_id: str | None = None) -> None:
        pass
