"""How a `PipeDocGen` step fills the Tables of its template file, part of the plugin contract.

A step's `table_fill` chooses it for every Table the step fills, and the render job carries it to the engine
(`RenderJob.table_fill`). `replace`, the default, writes a list's records over the Table's rows, growing or shrinking
it to the list's length, as engines always did. Any other fill is a capability an engine declares: its `doc_gen` model
lists the fill's token among its `inputs`, beside the sources it prints from, and a step asking for a fill its engine
does not declare is refused when the method loads (`resolve_doc_gen_setting`). An engine that predates a fill would
otherwise read the job, ignore the field and replace the Table's rows, losing the rows the template held.
"""

from enum import StrEnum

#: The token a `doc_gen` model lists among its `inputs` to declare that it appends records after a Table's last row.
TABLE_APPEND_CAPABILITY = "table_append"


class TableFill(StrEnum):
    """How a step fills the Tables of its template file."""

    REPLACE = "replace"
    """The records replace the Table's rows: the Table grows or shrinks to the list's length."""

    APPEND = "append"
    """The records are written after the Table's last row, which the Table grows to hold; it never shrinks."""

    @property
    def is_replace(self) -> bool:
        """Whether this is the default fill, which every engine that fills a template file does."""
        match self:
            case TableFill.REPLACE:
                return True
            case TableFill.APPEND:
                return False

    @property
    def engine_capability(self) -> str | None:
        """The token an engine's model lists among its `inputs` to declare this fill, None for the fill every engine does."""
        match self:
            case TableFill.REPLACE:
                return None
            case TableFill.APPEND:
                return TABLE_APPEND_CAPABILITY

    @property
    def desc(self) -> str:
        """What this fill does, for a message: 'append records to a Table'."""
        match self:
            case TableFill.REPLACE:
                return "replace a Table's rows with records"
            case TableFill.APPEND:
                return "append records to a Table"
