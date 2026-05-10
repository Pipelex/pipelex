from typing import Literal

from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef


class PipeStructureBlueprint(PipeBlueprint):
    type: Literal["PipeStructure"] = "PipeStructure"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None

    @override
    def validate_inputs(self):
        nb_inputs = self.nb_inputs
        if nb_inputs != 1:
            msg = (
                f"PipeStructure requires exactly one Text-compatible input, got {nb_inputs}: {self.input_names}. "
                "Declare a single input whose concept is Text or refines Text."
            )
            raise ValueError(msg)

    @override
    def validate_output(self):
        # String-level check on the output concept code. The full refinement check (catching
        # domain concepts that `refines = Text`) lives in `PipeStructure.validate_output_with_library`
        # — at the blueprint layer we only have the raw string, not a resolved Concept.
        output_parse_result = parse_concept_with_multiplicity(self.output)
        if QualifiedRef.parse(output_parse_result.concept_ref_or_code).local_code == NativeConceptCode.TEXT:
            msg = (
                f"PipeStructure output must be a structured concept, not Text. "
                f"Got '{self.output}'. PipeStructure exists to turn Text into structured data; "
                "use the input as-is if you want to keep Text."
            )
            raise ValueError(msg)
