from typing import Dict, List, Optional

from pydantic import Field, RootModel
from typing_extensions import override

from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_provider_abstract import PipeProviderAbstract
from pipelex.exceptions import ConceptError, ConceptLibraryConceptNotFoundError, PipeLibraryError, PipeLibraryPipeNotFoundError
from pipelex.hub import get_concept_provider

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeProviderAbstract):
    root: PipeLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        concept_provider = get_concept_provider()
        for pipe in self.root.values():
            try:
                for concept_code in pipe.concept_dependencies():
                    try:
                        concept_provider.get_required_concept(concept_code=concept_code)
                    except ConceptError as concept_error:
                        raise PipeLibraryError(
                            f"Error validating pipe '{pipe.code}' dependency concept '{concept_code}' because of: {concept_error}"
                        ) from concept_error
                for pipe_code in pipe.pipe_dependencies():
                    self.get_required_pipe(pipe_code=pipe_code)
                pipe.validate_with_libraries()
            except (ConceptLibraryConceptNotFoundError, PipeLibraryPipeNotFoundError) as not_found_error:
                raise PipeLibraryError(f"Missing dependency for pipe '{pipe.code}': {not_found_error}") from not_found_error

    def add_new_pipe(self, pipe: PipeAbstract):
        name = pipe.code
        pipe.inputs.set_default_domain(domain=pipe.domain)
        if pipe.output_concept_code and "." not in pipe.output_concept_code:
            pipe.output_concept_code = f"{pipe.domain}.{pipe.output_concept_code}"
        if name in self.root:
            raise PipeLibraryError(f"Pipe '{name}' already exists in the library")
        self.root[pipe.code] = pipe

    @override
    def get_optional_pipe(self, pipe_code: str) -> Optional[PipeAbstract]:
        return self.root.get(pipe_code)

    @override
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        the_pipe = self.get_optional_pipe(pipe_code=pipe_code)
        if not the_pipe:
            raise PipeLibraryPipeNotFoundError(
                f"Pipe '{pipe_code}' not found. Check for typos and make sure it is declared in a library listed in the config."
            )
        return the_pipe

    @override
    def get_pipes(self) -> List[PipeAbstract]:
        return list(self.root.values())

    @override
    def get_pipes_dict(self) -> Dict[str, PipeAbstract]:
        return self.root

    @override
    def teardown(self) -> None:
        self.root = {}
