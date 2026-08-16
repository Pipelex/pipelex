"""Suggested-fix wire models — structured, deterministic fixes attached to validation diagnostics.

Each fixable ``ValidationErrorItem`` carries a ``SuggestedFix``: semantic patch ops addressed
by TOML path, translated by the fix planner from enriched typed errors (never from message
strings). The ops are the machine contract; any rendered diff is presentation.

The op vocabulary is a **discriminated union on ``kind``**: each variant declares exactly the
fields its own semantics need, so a malformed op is refused by pydantic at parse time rather
than by a hand-written shape check deep inside the applier. It is published as two subsets —
:data:`FixOp`, every kind, for the ``.mthds`` fix path, and :data:`MigrationOp`, the structural
kinds only, for configuration migration ledgers. The narrower alias is what makes a ledger
containing a materializing op fail when the ledger is parsed. See ``docs/migration-ledger.md``.

This module is deliberately low-level (stdlib + pydantic only) so that
``pipelex.base_exceptions`` — where ``ValidationErrorItem`` lives — can import it without
creating an import cycle. Naming is brand-neutral: fixes are a language-level concept.
"""

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A TOML-representable value for a set_key op: a scalar (output refs, input refs), or a flat
# scalar mapping for fixes that create a whole table at once (written as an inline table —
# e.g. a missing `inputs` mapping). Deeper nesting would come with rules that need it.
TomlScalar: TypeAlias = str | int | float | bool
TomlValue: TypeAlias = TomlScalar | dict[str, TomlScalar]

# The wildcard path segment. It stands for "every entry of the open mapping at this node" — a
# field typed as a mapping from arbitrary user-chosen keys to a value schema, where the keys
# belong to the user and the value schema belongs to us. The applier expands it over the keys
# the document actually holds; deciding whether a given node really is open is the migration
# gate's job, since only the fingerprint knows.
WILDCARD_SEGMENT = "*"


class FixOpKind(StrEnum):
    """The semantic patch operations a suggested fix is composed of."""

    SET_KEY = "set_key"
    ENSURE_TABLE = "ensure_table"
    DELETE_KEY = "delete_key"
    DELETE_TABLE = "delete_table"
    RENAME_TABLE_KEY = "rename_table_key"
    MOVE_KEY = "move_key"
    REMAP_VALUE = "remap_value"

    @property
    def is_structural(self) -> bool:
        """Whether the kind only removes, renames or relocates material already in the file.

        The structural kinds are exactly the ones a migration ledger may contain. The
        materializing kinds write values that were not there, which is right when a typed error
        names the exact key to write and wrong under always-replay, where it would overwrite a
        user's choice on every run.
        """
        match self:
            case FixOpKind.SET_KEY | FixOpKind.ENSURE_TABLE:
                return False
            case FixOpKind.DELETE_KEY | FixOpKind.DELETE_TABLE | FixOpKind.RENAME_TABLE_KEY | FixOpKind.MOVE_KEY | FixOpKind.REMAP_VALUE:
                return True


class FixSafety(StrEnum):
    """Whether a fix is safe to auto-apply (SAFE) or requires explicit opt-in (UNSAFE)."""

    SAFE = "safe"
    UNSAFE = "unsafe"

    @property
    def is_safe(self) -> bool:
        match self:
            case FixSafety.SAFE:
                return True
            case FixSafety.UNSAFE:
                return False


class FixOpBase(BaseModel):
    """Fields every op shares: the table it acts in.

    ``table_path`` addresses the containing table (e.g. ``["pipe", "my_seq"]``), aligned with
    the ``field_path`` conventions of validation errors, and is empty for the document root.
    Variants add whatever their own semantics require, and nothing else — ``extra="forbid"``
    turns a field named on the wrong kind into a parse error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    table_path: list[str]


class SetKeyOp(FixOpBase):
    """Write ``key = value`` in the addressed table, whatever it currently holds."""

    kind: Literal[FixOpKind.SET_KEY] = FixOpKind.SET_KEY
    key: str
    value: TomlValue


class EnsureTableOp(FixOpBase):
    """Create the addressed table when it is absent, leaving an existing one untouched.

    Here ``table_path`` addresses the table to create, not its parent, so it cannot be empty:
    the document root always exists.
    """

    kind: Literal[FixOpKind.ENSURE_TABLE] = FixOpKind.ENSURE_TABLE
    table_path: list[str] = Field(min_length=1)


class DeleteKeyOp(FixOpBase):
    """Drop ``key`` from the addressed table."""

    kind: Literal[FixOpKind.DELETE_KEY] = FixOpKind.DELETE_KEY
    key: str


class DeleteTableOp(FixOpBase):
    """Drop the addressed table, including every chunk of one written out of order.

    ``table_path`` *is* the target rather than its parent, so it cannot be empty — deleting the
    document root is not a thing an op may express.
    """

    kind: Literal[FixOpKind.DELETE_TABLE] = FixOpKind.DELETE_TABLE
    table_path: list[str] = Field(min_length=1)


class RenameTableKeyOp(FixOpBase):
    """Rename ``key`` to ``new_key`` in place within the addressed table, keeping its position."""

    kind: Literal[FixOpKind.RENAME_TABLE_KEY] = FixOpKind.RENAME_TABLE_KEY
    key: str
    new_key: str


class MoveKeyOp(FixOpBase):
    """Relocate ``key`` from the addressed table into ``new_table_path``, under ``new_key``.

    The moved key may be table-valued, in which case the whole subtree travels. Destination
    parents that do not exist are created, as block tables, as part of the operation. Position
    is preserved within a parent and never across parents — see ``docs/migration-ledger.md``
    for the placement rule and for what happens to a moved table's introducing comment.
    """

    kind: Literal[FixOpKind.MOVE_KEY] = FixOpKind.MOVE_KEY
    key: str
    new_table_path: list[str]
    new_key: str

    @field_validator("new_table_path")
    @classmethod
    def refuse_wildcard_destination(cls, new_table_path: list[str]) -> list[str]:
        """A destination cannot be a wildcard: there would be no rule for which entry receives it.

        A wildcard *source* is unambiguous — it means "each of these" — but "move each entry's
        key into *some* entry" names no target. Should a real need for a mirrored source and
        destination appear, it wants an explicit correspondence rule, not this silence.
        """
        if WILDCARD_SEGMENT in new_table_path:
            msg = f"a move_key destination may not contain the wildcard segment '{WILDCARD_SEGMENT}'"
            raise ValueError(msg)
        return new_table_path

    @field_validator("table_path")
    @classmethod
    def refuse_wildcard_source(cls, table_path: list[str]) -> list[str]:
        """A move cannot start from a wildcard either, and for the same reason read the other way.

        With the destination pinned to one fixed key, "move each entry's key" is many-to-one: on
        any file where two matched entries carry the key, the second lands on a destination the
        first just occupied and the whole operation conflicts. The other kinds act on each matched
        entry in place, which is what makes a wildcard mean something for them.
        """
        if WILDCARD_SEGMENT in table_path:
            msg = f"a move_key source may not contain the wildcard segment '{WILDCARD_SEGMENT}': every matched entry would move onto one destination"
            raise ValueError(msg)
        return table_path


class RemapValueOp(FixOpBase):
    """Rewrite ``key``'s value through ``mapping``, doing nothing when it is not a mapped value.

    Only string values are remapped: the operation exists for renamed enumerated values, whose
    TOML representation is always a string.
    """

    kind: Literal[FixOpKind.REMAP_VALUE] = FixOpKind.REMAP_VALUE
    key: str
    mapping: dict[str, str] = Field(min_length=1)


# Every kind, for the `.mthds` fix path: a planner derives ops from one typed error about one
# key, so materializing ops are correct there.
FixOp: TypeAlias = Annotated[
    Union[SetKeyOp, EnsureTableOp, DeleteKeyOp, DeleteTableOp, RenameTableKeyOp, MoveKeyOp, RemapValueOp],
    Field(discriminator="kind"),
]

# The structural kinds only, for configuration migration ledgers, where every entry is replayed
# over every file on every run. Validating a ledger against this alias is what turns "a ledger
# must not materialize" from a review rule into a parse error.
MigrationOp: TypeAlias = Annotated[
    Union[DeleteKeyOp, DeleteTableOp, RenameTableKeyOp, MoveKeyOp, RemapValueOp],
    Field(discriminator="kind"),
]


class SuggestedFix(BaseModel):
    """A deterministic fix for one validation error, ready for a style-preserving applier.

    ``fix_code`` is the kebab-case rule id (e.g. ``"match-sequence-output"``). ``source`` is
    the file the ops target, when known (multi-file libraries) — an applier must only apply
    ops to the file they target.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fix_code: str
    description: str
    safety: FixSafety = Field(strict=False)
    source: str | None = None
    ops: list[FixOp]
