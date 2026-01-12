from pydantic import BaseModel, Field

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.domain.domain_library import DomainLibrary
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.libraries.pipe.pipe_library import PipeLibrary
from pipelex.pipe_controllers.pipe_controller import PipeController


class Library(BaseModel):
    """A Library bundles together domain, concept, and pipe libraries for a specific context.

    This represents a complete set of Pipelex definitions (domains, concepts, pipes)
    that can be loaded and used together, typically for a single pipeline run.

    Limitations: It lacks the Func Registry library and Class Registry library

    Each Library (except BASE) inherits native concepts and base pipes from the BASE library.
    """

    domain_library: DomainLibrary
    concept_library: ConceptLibrary
    pipe_library: PipeLibrary
    loaded_plx_paths: list[str] = Field(default_factory=list)

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
        self.loaded_plx_paths = []

    def validate_library(self) -> None:
        self.validate_pipe_library_with_libraries()
        self.validate_concept_library_with_libraries()
        self.validate_domain_library_with_libraries()

    def validate_pipe_library_with_libraries(self) -> None:
        for pipe in self.pipe_library.get_pipes():
            # Validate concept dependencies exist
            # Note: This should NEVER fail as concepts are validated during pipe construction via get_required_concept()
            # TODO: Make this non mandatory in production, or a test
            for concept in pipe.concept_dependencies:
                try:
                    self.concept_library.is_concept_exists(concept_ref=concept.concept_ref)
                except ConceptLibraryError as concept_error:
                    msg = (
                        f"INTERNAL ERROR: Pipe '{pipe.code}' references concept '{concept.concept_ref}' "
                        f"which doesn't exist in the concept library. This should be impossible as concepts are "
                        f"validated during pipe construction (via get_required_concept() in pipe factories). "
                        f"This indicates a bug in the system. Original error: {concept_error}"
                    )
                    raise PipelexUnexpectedError(msg) from concept_error

            # Validate pipe dependencies exist for pipe controllers
            if isinstance(pipe, PipeController):
                for sub_pipe_code in pipe.pipe_dependencies():
                    try:
                        self.pipe_library.get_required_pipe(pipe_code=sub_pipe_code)
                    except PipeLibraryError as pipe_error:
                        msg = f"Error validating pipe '{pipe.code}' dependency pipe '{sub_pipe_code}' because of: {pipe_error}"
                        raise LibraryError(msg) from pipe_error

        for pipe in self.pipe_library.root.values():
            pipe.validate_with_libraries()

    def validate_concept_library_with_libraries(self) -> None:
        pass

    def validate_domain_library_with_libraries(self) -> None:
        pass
