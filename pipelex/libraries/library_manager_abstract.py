from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry

from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

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

    def get_library_class_registry(self, library_id: str) -> ClassRegistry | None:  # ruff: ignore[unused-method-argument]
        """Get the ClassRegistry associated with a library, if any.

        Returns None by default. Overridden by LibraryManager.
        """
        return None

    def get_pipe_source(self, pipe_code: str) -> str | None:  # ruff: ignore[unused-method-argument]
        """Get the source identifier for a pipe.

        Args:
            pipe_code: The pipe code to look up.

        Returns:
            The source the pipe was loaded from — a filesystem path or a logical URI,
            preserved verbatim — or None if unknown.
        """
        return None

    def is_crate_loaded(self, *, library_id: str, fingerprint: str) -> bool:  # ruff: ignore[unused-method-argument]
        """Whether a crate with this fingerprint was already loaded into this library.

        Returns False by default (managers that don't track crate fingerprints report
        nothing as loaded). Overridden by LibraryManager, which keeps per-library
        fingerprint bookkeeping for load idempotency.

        Args:
            library_id: The library to query.
            fingerprint: The crate fingerprint to look up.

        Returns:
            True when the crate is already loaded into the library, False otherwise
            (including when the library_id is unknown).
        """
        return False

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
    def load_from_crate(self, *, library_id: str, crate: LibraryCrate) -> list[PipeAbstract]:
        """Load a LibraryCrate into a live Library.

        Note: This method does NOT resolve cross-package address-based dependencies.
        Callers must handle dependency loading before calling this method.

        Args:
            library_id: The library to load into
            crate: The LibraryCrate containing qualified blueprints, domain metadata, and source info
        """

    @abstractmethod
    def load_from_blueprints(self, *, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def _remove_from_blueprint(self, *, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        pass

    @abstractmethod
    def _remove_from_blueprints(self, *, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        pass

    @abstractmethod
    def load_libraries(
        self,
        *,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list[PipeAbstract]:
        pass
