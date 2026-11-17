"""What an engine's template checker takes and returns, part of the plugin contract.

An office template names the fields it is filled with in its own way: an Excel workbook through its defined
names and Tables, a Word document through its tags, a PowerPoint deck through its shape names. Pipelex cannot
read those, so an engine that fills a template file overrides its worker's `check_template`
(`DocGenWorkerAbstract`). The dry run, and so `pipelex validate`, calls it for every `PipeDocGen` step with a
`template_file`, before anything is spent: an error finding fails the step, and a warning joins the validation
verdict's advisory `warnings` as a `template_check_warning` item, or is logged by a dry run that returns no verdict.
Either way a finding's words reach whoever validates the method, so they are written for the template's author.
The built-in PDF engine takes no template, and Pipelex checks HTML templates itself, so neither needs one.
"""

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.input_shape import InputShape
from pipelex.cogt.doc_gen.sheet_range import SheetRangeFill
from pipelex.cogt.doc_gen.table_fill import CellPolicy, TableFill, sheet_range_refusal, table_match_refusal


class TemplateFindingSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"

    @property
    def is_error(self) -> bool:
        """Whether a finding of this severity fails the step, rather than being reported as an advisory warning."""
        match self:
            case TemplateFindingSeverity.ERROR:
                return True
            case TemplateFindingSeverity.WARNING:
                return False


class TemplateFinding(BaseModel):
    """One thing a checker found in a template file."""

    severity: TemplateFindingSeverity = Field(strict=False)
    message: str = Field(description="What is wrong, in the template author's words: the name, the field, the fix")
    location: str | None = Field(default=None, description="Where it is in the file, such as 'the Table LineItems on sheet Invoice'")


class TemplateCheckRequest(BaseModel):
    """A template file and the inputs it is filled with, for a checker to compare.

    It carries the step's fill as the render job does (`RenderJob`): `table_fill`, and under `update` how a record finds
    its row, `match_on` or `match_row`, and `cells`. A checker that knows the update refuses what the fill would, such
    as a `match_on` field no column of a filled Table matches, or a field that matches a calculated column, and fills
    the template in memory the way the job would; a checker that does not ignores them, and is never handed an update,
    since a step asking its engine for a fill it does not declare is refused when the method loads.

    Under `update`, the dry run sends no `data`: its mock records cannot match the template's real rows, so the checker
    judges the template's structure alone. A Table filled from a list whose records lack a `match_on` or `match_row`
    field is an error finding, which fails the step: the method's load holds only some list of the step's data to those
    fields, since only the engine knows which list fills which Table.

    Under `append` or `update` it may carry `sheet_range`, the range on a sheet one list fills, as the render job does. A
    checker resolves it with the shared range finder (`pipelex.cogt.doc_gen.sheet_range`) and may let the finder's
    refusals (`SHEET_RANGE_REFUSALS`) propagate: Pipelex reports each as an error finding, naming the sheet and the cell.
    """

    model_config = ConfigDict(extra="forbid", ser_json_bytes="base64", val_json_bytes="base64")

    format: DocGenFormat = Field(strict=False)
    template: bytes = Field(description="The template file's bytes")
    template_name: str = Field(description="The template file as the method names it, for messages")
    inputs: dict[str, InputShape] = Field(description="The step's declared inputs by name, as the shape of their plain data")
    data: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Mock inputs as plain data, shaped as `RenderJob.data` is, so the checker can fill the template in memory and report "
            "what the fill would raise; None when only the structure is to be compared, as at run setup and, under `update`, "
            "at the dry run"
        ),
    )
    table_fill: TableFill = Field(default=TableFill.REPLACE, strict=False, description="How the step fills the template's Tables")
    match_on: list[str] | None = Field(default=None, description="Under `update`, the fields of the records whose columns are the Table's key")
    match_row: str | None = Field(default=None, description="Under `update`, the field of the records holding the row's position")
    cells: CellPolicy | None = Field(default=None, strict=False, description="Under `update`, which cells of a matched row may be written")
    sheet_range: SheetRangeFill | None = Field(default=None, description="Under `append` or `update`, the range on a sheet one list fills")

    @model_validator(mode="after")
    def validate_table_match(self) -> Self:
        match_refusal = table_match_refusal(table_fill=self.table_fill, match_on=self.match_on, match_row=self.match_row, cells=self.cells)
        if match_refusal is not None:
            msg = f"A template check request cannot match records to rows this way: {match_refusal}."
            raise ValueError(msg)
        range_refusal = sheet_range_refusal(table_fill=self.table_fill, sheet_range=self.sheet_range)
        if range_refusal is not None:
            msg = f"A template check request cannot fill a range on a sheet this way: {range_refusal}."
            raise ValueError(msg)
        return self
