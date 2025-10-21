from pydantic import BaseModel

from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.library import Library
from pipelex.libraries.pipe.pipe_library import PipeLibrary


class LibraryFactory(BaseModel):
    @classmethod
    def make_empty(cls) -> Library:
        # 1 - Concept library, add the native concepts
        concept_library = ConceptLibrary.make_empty()

        # 2 - Pipe library, add the builder pipes
        pipe_library = PipeLibrary.make_empty()

        # 3 - Domain library, add the domains
        domain_library = DomainLibrary.make_empty()

        return Library(domain_library=domain_library, concept_library=concept_library, pipe_library=pipe_library)
