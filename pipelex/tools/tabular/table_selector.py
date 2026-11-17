"""Which rows of a table file a `PipeStructure` step reads: its `table` or its `sheet_range`, or neither.

The selector crosses the content generator's leaf as plain data (`TableReadAssignment`), so a host runtime that
dispatches the read to another process carries it whole.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.doc_gen.sheet_range import SheetRange


class TableSelector(BaseModel):
    """The step's choice of the rows it reads in a workbook, at most one of two:

    - `table`, an Excel Table or, when the workbook holds no Table of that name, a named range, compared ignoring case;
    - `sheet_range`, a range on a worksheet, which reads the worksheet's one Table when it holds one.

    With neither, the workbook's only Table is read. A CSV file is one table, and is refused with either.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    table: str | None = Field(default=None, description="The Excel Table or named range to read; None for none")
    sheet_range: SheetRange | None = Field(default=None, description="The range on a worksheet to read; None for none")

    @model_validator(mode="after")
    def validate_one_choice(self) -> Self:
        if self.table is not None and self.sheet_range is not None:
            msg = "A step reads a Table or a named range by its name, or a range on a sheet, not both."
            raise ValueError(msg)
        return self

    @property
    def is_default(self) -> bool:
        """Whether the step names nothing, and so reads a workbook's only Table."""
        return self.table is None and self.sheet_range is None
