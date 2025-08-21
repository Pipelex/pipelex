from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.libraries.library_config import LibraryConfig
from pipelex.libraries.library_manager import LibraryManager


class LibraryManagerFactory:
    """Factory for creating LibraryManager instances."""

    @classmethod
    def make_empty(cls, config_dir_path: str) -> "LibraryManager":
        domain_library = DomainLibrary.make_empty()
        concept_library = ConceptLibrary.make_empty()
        pipe_library = PipeLibrary.make_empty()
        library_config = LibraryConfig(config_dir_path=config_dir_path)

        return LibraryManager(
            domain_library=domain_library,
            concept_library=concept_library,
            pipe_library=pipe_library,
            library_config=library_config,
        )

    @classmethod
    def make(
        cls, domain_library: DomainLibrary, concept_library: ConceptLibrary, pipe_library: PipeLibrary, config_dir_path: str
    ) -> "LibraryManager":
        """Create a LibraryManager with provided libraries."""

        library_config = LibraryConfig(config_dir_path=config_dir_path)

        return LibraryManager(
            domain_library=domain_library,
            concept_library=concept_library,
            pipe_library=pipe_library,
            library_config=library_config,
        )
