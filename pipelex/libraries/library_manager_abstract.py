from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.libraries.library_crate import LibraryCrate

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
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
    def open_fresh_library(self, library_id: str) -> "Library":
        """Open a library guaranteed to be empty, tearing down any pre-existing library under this id.

        For callers that reuse a deterministic library_id across executions (e.g. a Temporal
        workflow keyed by its workflow id): a pre-existing library under such an id can only be
        the leftover of an interrupted predecessor execution whose cleanup never ran. Reusing it
        is poison — its crate fingerprints would dedup-skip a fresh crate load while a freshly
        attached ClassRegistry no longer holds the crate's dynamic classes.
        """

    @abstractmethod
    def get_library(self, library_id: str) -> "Library":
        """Get the Library object for a specific library_id."""

    @abstractmethod
    def get_current_library(self) -> "Library":
        """Get the Library object for the current library."""

    def get_library_class_registry(self, library_id: str) -> ClassRegistry | None:  # noqa: ARG002
        """Get the ClassRegistry associated with a library, if any.

        Returns None by default. Overridden by LibraryManager.
        """
        return None

    def get_pipe_source(self, pipe_code: str) -> str | None:  # noqa: ARG002
        """Get the source identifier for a pipe.

        Args:
            pipe_code: The pipe code to look up.

        Returns:
            The source the pipe was loaded from — a filesystem path or a logical URI,
            preserved verbatim — or None if unknown.
        """
        return None

    @abstractmethod
    def get_crate(self, library_id: str) -> LibraryCrate | None:
        """Build a LibraryCrate from all accumulated blueprints for a given library_id.

        Returns None if the library_id is unknown or no blueprints were loaded.

        Args:
            library_id: The library to get the crate for

        Returns:
            A LibraryCrate built from all accumulated blueprints, or None
        """

    @abstractmethod
    def load_from_crate(self, library_id: str, *, crate: LibraryCrate) -> list[PipeAbstract]:
        """Load a LibraryCrate into a live Library.

        Note: This method does NOT resolve cross-package address-based dependencies.
        Callers must handle dependency loading before calling this method.

        Args:
            library_id: The library to load into
            crate: The LibraryCrate containing qualified blueprints, domain metadata, and source info
        """

    @abstractmethod
    def load_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def load_concepts_only_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> list["Concept"]:
        """Load only domains and concepts from blueprints, skipping pipes.

        This is a lightweight alternative to load_from_blueprints() that only processes
        domains and concepts. It does not load pipes, does not perform pipe validation,
        and does not run library.validate_library().

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed MTHDS blueprints to load

        Returns:
            List of all concepts that were loaded
        """

    @abstractmethod
    def _remove_from_blueprint(self, library_id: str, *, blueprint: PipelexBundleBlueprint) -> None:
        pass

    @abstractmethod
    def _remove_from_blueprints(self, library_id: str, *, blueprints: list[PipelexBundleBlueprint]) -> None:
        pass

    @abstractmethod
    def load_libraries(
        self,
        library_id: str,
        *,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def load_libraries_concepts_only(
        self,
        library_id: str,
        *,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list["Concept"]:
        """Load only domains and concepts from library directories, skipping pipes.

        This is a lightweight alternative to load_libraries() that only processes
        domains and concepts. It does not load pipes, does not perform pipe validation,
        and does not run library.validate_library().

        Args:
            library_id: The ID of the library to load into
            library_dirs: List of directories containing MTHDS files
            library_file_paths: List of specific MTHDS file paths to load

        Returns:
            List of all concepts that were loaded
        """
