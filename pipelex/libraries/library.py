from pydantic import BaseModel

from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.exceptions import (
    ConceptError,
    ConceptLibraryConceptNotFoundError,
    PipeLibraryError,
    PipeLibraryPipeNotFoundError,
)


class Library(BaseModel):
    """A Library bundles together domain, concept, and pipe libraries for a specific context.

    This represents a complete set of Pipelex definitions (domains, concepts, pipes)
    that can be loaded and used together, typically for a single pipeline run.

    Each Library (except BASE) inherits native concepts and base pipes from the BASE library.
    """

    domain_library: DomainLibrary
    concept_library: ConceptLibrary
    pipe_library: PipeLibrary

    def get_domain_library(self) -> DomainLibrary:
        return self.domain_library

    def get_concept_library(self) -> ConceptLibrary:
        return self.concept_library

    def get_pipe_library(self) -> PipeLibrary:
        return self.pipe_library

    def teardown(self) -> None:
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def validate_library(self) -> None:
        self.validate_pipe_library_with_libraries()

    def validate_pipe_library_with_libraries(self) -> None:
        for pipe in self.pipe_library.root.values():
            try:
                # Validate concept dependencies exit
                for concept in pipe.concept_dependencies():
                    try:
                        self.concept_library.get_required_concept(concept_string=concept.concept_string)
                    except ConceptError as concept_error:
                        msg = f"Error validating pipe '{pipe.code}' dependency concept '{concept.concept_string}' because of: {concept_error}"
                        raise PipeLibraryError(msg) from concept_error

                # Validate pipe dependencies exit
                for pipe_code in pipe.pipe_dependencies():
                    self.pipe_library.get_required_pipe(pipe_code=pipe_code)

            except (ConceptLibraryConceptNotFoundError, PipeLibraryPipeNotFoundError) as not_found_error:
                msg = f"Missing dependency for pipe '{pipe.code}': {not_found_error}"
                raise PipeLibraryError(msg) from not_found_error
        for pipe in self.pipe_library.root.values():
            pipe.validate_with_libraries()
