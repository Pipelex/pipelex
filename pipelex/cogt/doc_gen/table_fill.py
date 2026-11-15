"""How a `PipeDocGen` step fills the Tables of its template file, part of the plugin contract.

A step's `table_fill` chooses it for every Table the step fills, and the render job carries it to the engine
(`RenderJob.table_fill`). `replace`, the default, writes a list's records over the Table's rows, growing or shrinking
it to the list's length, as engines always did. Any other fill is a capability an engine declares: its `doc_gen` model
lists the fill's token among its `inputs`, beside the sources it prints from, and a step asking for a fill its engine
does not declare is refused when the method loads (`resolve_doc_gen_setting`). An engine that predates a fill would
otherwise read the job, ignore the field and replace the Table's rows, losing the rows the template held.

An `update` writes the records into rows the Table already holds, and so says how a record finds its row and which
cells it may write: `match_on`, the fields whose columns are the Table's key, or `match_row`, the field holding the
row's position among the Table's data rows, and `cells`, the `CellPolicy`. The render job and the template check
request carry the three beside `table_fill`, set under `update` and absent under any other fill, a rule
`table_match_refusal` states once for every model that carries them.
"""

from enum import StrEnum

#: The token a `doc_gen` model lists among its `inputs` to declare that it appends records after a Table's last row.
TABLE_APPEND_CAPABILITY = "table_append"

#: The token a `doc_gen` model lists among its `inputs` to declare that it updates the rows a Table holds, by key or by
#: row position, honouring the update's rules (`RenderJob`).
TABLE_UPDATE_CAPABILITY = "table_update"


class TableFill(StrEnum):
    """How a step fills the Tables of its template file."""

    REPLACE = "replace"
    """The records replace the Table's rows: the Table grows or shrinks to the list's length."""

    APPEND = "append"
    """The records are written after the Table's last row, which the Table grows to hold; it never shrinks."""

    UPDATE = "update"
    """Each record is written into the one row it matches, by key or by row position; no row is added or removed."""

    @property
    def is_replace(self) -> bool:
        """Whether this is the default fill, which every engine that fills a template file does."""
        match self:
            case TableFill.REPLACE:
                return True
            case TableFill.APPEND | TableFill.UPDATE:
                return False

    @property
    def is_update(self) -> bool:
        """Whether the records are written into the rows they match, which needs a way to match them and a cell policy."""
        match self:
            case TableFill.UPDATE:
                return True
            case TableFill.REPLACE | TableFill.APPEND:
                return False

    @property
    def engine_capability(self) -> str | None:
        """The token an engine's model lists among its `inputs` to declare this fill, None for the fill every engine does."""
        match self:
            case TableFill.REPLACE:
                return None
            case TableFill.APPEND:
                return TABLE_APPEND_CAPABILITY
            case TableFill.UPDATE:
                return TABLE_UPDATE_CAPABILITY

    @property
    def desc(self) -> str:
        """What this fill does, for a message: 'append records to a Table'."""
        match self:
            case TableFill.REPLACE:
                return "replace a Table's rows with records"
            case TableFill.APPEND:
                return "append records to a Table"
            case TableFill.UPDATE:
                return "update a Table's rows with records"


class CellPolicy(StrEnum):
    """Which cells of a matched row an `update` may write. A null field writes nothing under either."""

    FILL_EMPTY = "fill_empty"
    """Only an empty cell is written; a non-empty cell holding a different value is a conflict that fails the fill."""

    OVERWRITE = "overwrite"
    """Every cell a non-null field matches is written, whatever it held: the explicit opt-in for corrections."""


def table_match_refusal(*, table_fill: TableFill, match_on: list[str] | None, match_row: str | None, cells: CellPolicy | None) -> str | None:
    """Why a job's or a request's matching fields do not fit its fill, as a clause of a message, or None when they fit.

    An `update` names exactly one way to match, `match_on`, at least one field and no field twice, or `match_row`, and
    its `cells`, which Pipelex resolves before it hands either model over, so an engine never decides a default. Any
    other fill carries none of the three.
    """
    if not table_fill.is_update:
        carried = [name for name, value in (("match_on", match_on), ("match_row", match_row), ("cells", cells)) if value is not None]
        if carried:
            return f"its fill '{table_fill}' matches no row, so it carries no {', '.join(carried)}"
        return None
    if (match_on is None) == (match_row is None):
        return "an update matches each record to its row by exactly one of match_on and match_row"
    if match_on is not None:
        if not match_on:
            return "an update's match_on names at least one field"
        if len(set(match_on)) != len(match_on):
            return "an update's match_on names each field once"
    if cells is None:
        return "an update carries its cell policy, cells"
    return None
