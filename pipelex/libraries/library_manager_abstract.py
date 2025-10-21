from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.pipes.pipe_abstract import PipeAbstract

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
    def create_library(self, library_id: str) -> None:
        """Create a new library with the given library_id."""

    @abstractmethod
    def set_library(self, library_id: str, library: "Library") -> None:
        """Set the Library object for a specific library_id."""

    @abstractmethod
    def open_library(self, library_id: str) -> None:
        """Open a new library with the given library_id."""

    @abstractmethod
    def get_library(self, library_id: str | None = None) -> "Library":
        """Get the Library object for a specific library_id."""

    @abstractmethod
    def load_libraries(
        self,
        library_id: str | None = None,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        pass

    @abstractmethod
    def load_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def remove_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        pass
