from pydantic import BaseModel

from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.pipes.pipe_library import PipeLibrary


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
        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()
