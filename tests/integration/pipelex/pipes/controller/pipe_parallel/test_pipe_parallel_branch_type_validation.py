from typing import Callable

import pytest
from pydantic import Field

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry, get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class BtvCombinedResult(StructuredContent):
    """Structured combination target with content-typed fields."""

    summary: TextContent = Field(description="Summary of the analysis")
    score: NumberContent = Field(description="Numeric score of the analysis")


DOMAIN_CODE = "test_btv"


class TestPipeParallelBranchTypeValidation:
    """validate_output_with_library must check branch output TYPES against structured fields, not just names."""

    def _setup_library(self, *, score_branch_output: str) -> PipeParallel:
        """Build a library with a parallel whose 'score' branch outputs the given concept ref."""
        get_class_registry().register_class(BtvCombinedResult)

        concept_library = get_concept_library()
        combined_concept = ConceptFactory.make(
            concept_code="BtvCombinedResult",
            domain_code=DOMAIN_CODE,
            description="Combined analysis result",
            structure_class_name="BtvCombinedResult",
        )
        refined_text_concept = ConceptFactory.make_from_blueprint(
            domain_code=DOMAIN_CODE,
            concept_code="BtvSummary",
            blueprint_or_string_description=ConceptBlueprint(description="A summary", refines="Text"),
        )
        refined_number_concept = ConceptFactory.make_from_blueprint(
            domain_code=DOMAIN_CODE,
            concept_code="BtvScore",
            blueprint_or_string_description=ConceptBlueprint(description="A score", refines="Number"),
        )
        concept_library.add_concepts(concepts=[combined_concept, refined_text_concept, refined_number_concept])

        pipe_library = get_pipe_library()
        summary_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=DOMAIN_CODE,
            pipe_code="btv_summarize",
            blueprint=PipeLLMBlueprint(
                description="Summarize the input",
                inputs={"input_text": "Text"},
                output=f"{DOMAIN_CODE}.BtvSummary",
                prompt="Summarize: $input_text",
            ),
            concept_codes_from_the_same_domain=["BtvSummary", "BtvScore", "BtvCombinedResult"],
        )
        score_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=DOMAIN_CODE,
            pipe_code="btv_scoring",
            blueprint=PipeLLMBlueprint(
                description="Score the input",
                inputs={"input_text": "Text"},
                output=score_branch_output,
                prompt="Score: $input_text",
            ),
            concept_codes_from_the_same_domain=["BtvSummary", "BtvScore", "BtvCombinedResult"],
        )
        pipe_library.add_new_pipe(pipe=summary_pipe)
        pipe_library.add_new_pipe(pipe=score_pipe)

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=DOMAIN_CODE,
            pipe_code="btv_parallel",
            blueprint=PipeParallelBlueprint(
                description="Parallel combining summary and score",
                inputs={"input_text": "Text"},
                output=f"{DOMAIN_CODE}.BtvCombinedResult",
                branches=[
                    SubPipeBlueprint(pipe="btv_summarize", result="summary"),
                    SubPipeBlueprint(pipe="btv_scoring", result="score"),
                ],
            ),
            concept_codes_from_the_same_domain=["BtvSummary", "BtvScore", "BtvCombinedResult"],
        )
        pipe_library.add_new_pipe(pipe=pipe_parallel)
        return pipe_parallel

    def test_compatible_branch_types_validate_clean(self, load_empty_library: Callable[[], str]):
        """Refinement is conceptual compatibility: refines-Text fits TextContent, refines-Number fits NumberContent."""
        load_empty_library()
        pipe_parallel = self._setup_library(score_branch_output=f"{DOMAIN_CODE}.BtvScore")

        pipe_parallel.validate_output_with_library()

    def test_incompatible_branch_type_raises(self, load_empty_library: Callable[[], str]):
        """A branch producing text into a NumberContent-typed field must fail /validate, not the runtime combine."""
        load_empty_library()
        pipe_parallel = self._setup_library(score_branch_output=f"{DOMAIN_CODE}.BtvSummary")

        with pytest.raises(PipeValidationError, match="score"):
            pipe_parallel.validate_output_with_library()
