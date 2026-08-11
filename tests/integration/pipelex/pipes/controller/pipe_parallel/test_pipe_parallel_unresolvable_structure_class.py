from typing import Callable

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.runtime_hub import get_class_registry

DOMAIN_CODE = "test_usc"


class UscRegisteredCombined(StructuredContent):
    """Registered combination target, used to reach the per-branch structure-class lookup."""

    summary: TextContent = Field(description="Summary produced by the branch")


class TestPipeParallelUnresolvableStructureClass:
    """A missing structure class must surface as PipeValidationError, not a raw ConceptValueError.

    The `/validate` sweep only catches Pipelex-typed errors around per-pipe validation, so a
    bare ConceptValueError (a plain ValueError) escaping `validate_output_with_library` would
    abort the whole bundle instead of failing just this pipe.
    """

    def _setup_library(self, *, output_concept_code: str, branch_output_concept_code: str) -> PipeParallel:
        """Build a parallel whose output (or branch output) concept has an unregistered structure class."""
        concept_library = get_concept_library()
        for concept_code in {output_concept_code, branch_output_concept_code}:
            structure_class_name = "UscRegisteredCombined" if concept_code == "UscRegisteredCombined" else f"{concept_code}UnregisteredStructure"
            concept = ConceptFactory.make(
                concept_code=concept_code,
                domain_code=DOMAIN_CODE,
                description=f"Concept {concept_code}",
                structure_class_name=structure_class_name,
            )
            concept_library.add_concepts(concepts=[concept])

        pipe_library = get_pipe_library()
        branch_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=DOMAIN_CODE,
            pipe_code="usc_branch",
            blueprint=PipeLLMBlueprint(
                description="Branch producing the summary",
                inputs={"input_text": "Text"},
                output=f"{DOMAIN_CODE}.{branch_output_concept_code}" if branch_output_concept_code != "Text" else "Text",
                prompt="Summarize: $input_text",
            ),
            concept_codes_from_the_same_domain=[output_concept_code, branch_output_concept_code],
        )
        pipe_library.add_new_pipe(pipe=branch_pipe)

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=DOMAIN_CODE,
            pipe_code="usc_parallel",
            blueprint=PipeParallelBlueprint(
                description="Parallel with an unresolvable output structure class",
                inputs={"input_text": "Text"},
                output=f"{DOMAIN_CODE}.{output_concept_code}",
                branches=[
                    SubPipeBlueprint(pipe="test_usc.usc_branch", result="summary"),
                ],
            ),
            concept_codes_from_the_same_domain=[output_concept_code, branch_output_concept_code],
        )
        pipe_library.add_new_pipe(pipe=pipe_parallel)
        return pipe_parallel

    def test_unregistered_output_structure_class_raises_pipe_validation_error(self, load_empty_library: Callable[[], str]):
        """The parallel's own output concept resolves to no registered class: must be a PipeValidationError."""
        load_empty_library()
        pipe_parallel = self._setup_library(output_concept_code="UscCombined", branch_output_concept_code="UscCombined")

        with pytest.raises(PipeValidationError, match="UscCombined"):
            pipe_parallel.validate_output_with_library()

    def test_unregistered_branch_structure_class_raises_pipe_validation_error(self, load_empty_library: Callable[[], str]):
        """A branch output concept resolving to no registered class: must be a PipeValidationError too."""
        load_empty_library()
        get_class_registry().register_class(UscRegisteredCombined)
        pipe_parallel = self._setup_library(output_concept_code="UscRegisteredCombined", branch_output_concept_code="UscBranchOnly")

        with pytest.raises(PipeValidationError, match="UscBranchOnly"):
            pipe_parallel.validate_output_with_library()
