from typing import Literal

from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint


class PipeStructureBlueprint(PipeBlueprint):
    type: Literal["PipeStructure"] = "PipeStructure"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    # The spreadsheet path, when the single input is a `Document` or refines it: the Excel Table to read, `None` for the
    # workbook's only one, and the output field that receives each row's position among the table's data rows. Both
    # are refused on the Text path; the blueprint cannot tell the two paths apart from the input's concept string, so
    # `PipeStructure.validate_inputs_with_library` checks them once the concepts resolve.
    table: str | None = None
    row_field: str | None = None

    @override
    def validate_inputs(self):
        nb_inputs = self.nb_inputs
        if nb_inputs != 1:
            msg = (
                f"PipeStructure requires exactly one input, got {nb_inputs}: {self.input_names}. "
                "Declare a single input whose concept is Text or refines Text, or Document or refines Document to read a spreadsheet."
            )
            raise ValueError(msg)

        # Reject multiplicity (Text[], Document[N]) at the blueprint layer. The runtime reads the
        # input as a single TextContent or DocumentContent, and would otherwise crash on a ListContent
        # with an opaque error. Users with a list of texts or workbooks should wrap PipeStructure in a PipeBatch.
        input_name, input_concept_spec = next(iter((self.inputs_concept_specs or {}).items()))
        input_parse_result = parse_concept_with_multiplicity(input_concept_spec)
        if input_parse_result.multiplicity is not None:
            msg = (
                f"PipeStructure input '{input_name}' = '{input_concept_spec}' carries multiplicity, "
                "but PipeStructure operates on a single Text or a single Document. "
                "Wrap PipeStructure in a PipeBatch to structure each item of a list."
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
                f"Got '{self.output}'. PipeStructure exists to turn Text, or a spreadsheet, into structured data; "
                "use the input as-is if you want to keep Text."
            )
            raise ValueError(msg)
