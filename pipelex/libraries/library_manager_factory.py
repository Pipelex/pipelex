"""Factory for creating LibraryManager instances."""

from typing import Optional

from pipelex.core.concept_library import ConceptLibrary
from pipelex.core.domain_library import DomainLibrary
from pipelex.core.pipe_library import PipeLibrary
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager import LibraryManager


class LibraryManagerFactory:
    """Factory class for creating LibraryManager instances."""

    @classmethod
    def make_empty(cls, config_folder_path: str) -> LibraryManager:
        """Create an empty LibraryManager with the given config folder path.

        Args:
            config_folder_path: Path to the configuration folder

        Returns:
            LibraryManager: A new empty LibraryManager instance
        """
        LibraryManager.domain_library = DomainLibrary.make_empty()
        LibraryManager.concept_library = ConceptLibrary.make_empty()
        LibraryManager.pipe_library = PipeLibrary.make_empty()
        LibraryManager.library_config = LibraryConfig(config_folder_path=config_folder_path)
        return LibraryManager()

    @classmethod
    def make(
        cls,
        domain_library: Optional[DomainLibrary],
        concept_library: Optional[ConceptLibrary],
        pipe_library: Optional[PipeLibrary],
        config_folder_path: str,
    ) -> LibraryManager:
        """Create a LibraryManager instance with the given libraries.

        Args:
            domain_library: The domain library to use
            concept_library: The concept library to use
            pipe_library: The pipe library to use
            config_folder_path: Path to the configuration folder

        Returns:
            LibraryManager: A new LibraryManager instance
        """
        LibraryManager.domain_library = domain_library or DomainLibrary.make_empty()
        LibraryManager.concept_library = concept_library or ConceptLibrary.make_empty()
        LibraryManager.pipe_library = pipe_library or PipeLibrary.make_empty()
        LibraryManager.library_config = LibraryConfig(config_folder_path=config_folder_path)
        return LibraryManager()
