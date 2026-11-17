from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint


class SheetRangeBlueprint(BaseModel):
    """A range of rows on a worksheet that holds no Excel Table: `PipeStructure`'s `sheet_range`.

    `sheet` names the worksheet, compared ignoring case; without it the workbook must hold exactly one worksheet.
    `header_row` is the sheet row holding the header, counted from 1 as the spreadsheet numbers its rows; without it the
    header is the sheet's first row holding a value. `sheet_range = {}` reads the only worksheet and finds its header. A
    worksheet holding one Excel Table reads as that Table. The rules the runtime finds the range by, and refuses an
    unclear one by, are those of the standard's "Finding a Sheet Range".
    """

    model_config = ConfigDict(extra="forbid")

    sheet: str | None = None
    header_row: Annotated[int, Field(ge=1, strict=True)] | None = None


class PipeStructureBlueprint(PipeBlueprint):
    type: Literal["PipeStructure"] = "PipeStructure"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    # The spreadsheet path, when the single input is a `Document` or refines it: the Excel Table or named range to read,
    # or the range on a sheet, at most one of the two, neither for the workbook's only Table; and the output field that
    # receives each row's position among the table's data rows. All three are refused on the Text path; the blueprint
    # cannot tell the two paths apart from the input's concept string, so `PipeStructure.validate_inputs_with_library`
    # checks them once the concepts resolve.
    table: str | None = None
    sheet_range: SheetRangeBlueprint | None = None
    row_field: str | None = None

    @model_validator(mode="after")
    def validate_one_region(self) -> Self:
        if self.table is not None and self.sheet_range is not None:
            msg = (
                "PipeStructure's 'table' names an Excel Table or a named range, and 'sheet_range' a range on a sheet: "
                "a step reads one of them, so use 'table' or 'sheet_range', not both."
            )
            raise ValueError(msg)
        return self

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
