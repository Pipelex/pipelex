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
    def teardown(self, library_id: str | None = None) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def open_library(self, library_id: str | None = None) -> tuple[str, "Library"]:
        """Open a library with the given library_id. Creates it if it doesn't exist. If no library_id is provided, it creates one."""

    @abstractmethod
    def get_library(self, library_id: str) -> "Library":
        """Get the Library object for a specific library_id."""

    @abstractmethod
    def get_current_library(self) -> "Library":
        """Get the Library object for the current library."""

    def get_pipe_source(self, pipe_code: str) -> Path | None:  # noqa: ARG002
        """Get the source file path for a pipe.

        Args:
            pipe_code: The pipe code to look up.

        Returns:
            Path to the .plx file the pipe was loaded from, or None if unknown.
        """
        return None

    @abstractmethod
    def load_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def _remove_from_blueprint(self, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        pass

    @abstractmethod
    def _remove_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        pass

    @abstractmethod
    def load_libraries(
        self,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list[PipeAbstract]:
        pass
