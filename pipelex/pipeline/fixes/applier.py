"""Style-preserving fix applier — applies ``FixOp`` patch ops to a tomlkit DOM in place.

In-place mutation, never container rebuilds: tomlkit keeps the comments, ordering, and
table style of untouched content (and of the patched line itself) by construction.

Guarded application: an op only applies when its target table path exists in the DOM.
This protects against errors raised on elaborated/synthetic constructs (a synthesized
sequence has no TOML to patch) and against ops targeting a different file than the one
being patched — a skipped op is reported, never raised.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field
from tomlkit import TOMLDocument
from tomlkit.items import InlineTable

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.suggested_fix import FixOp, FixOpKind, TomlValue


class FixOpOutcome(StrEnum):
    """What happened to one op during application."""

    APPLIED = "applied"
    SKIPPED = "skipped"

    @property
    def did_apply(self) -> bool:
        match self:
            case FixOpOutcome.APPLIED:
                return True
            case FixOpOutcome.SKIPPED:
                return False


class FixOpApplication(BaseModel):
    """Per-op application report: the op, whether it applied, and why not when skipped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: FixOp
    outcome: FixOpOutcome = Field(strict=False)
    detail: str | None = None


def _resolve_table(toml_doc: TOMLDocument, *, table_path: list[str]) -> dict[str, Any] | None:
    """Walk ``table_path`` down the DOM, returning the addressed table or ``None`` when absent.

    Every segment must resolve to a dict-like container (tomlkit tables and inline tables
    all subclass ``dict``); a missing or non-table segment means the target does not exist.
    """
    node = cast("dict[str, Any]", toml_doc)
    for segment in table_path:
        candidate = node.get(segment)
        if not isinstance(candidate, dict):
            return None
        node = cast("dict[str, Any]", candidate)
    return node


def _as_tomlkit_value(value: TomlValue | None) -> Any:
    """Convert a mapping value to a canonical inline table (`inputs = { ... }`, the dominant
    authoring form); scalars pass through, tomlkit wraps them itself on assignment.
    """
    if isinstance(value, dict):
        return _canonical_inline_table(value)
    return value


def _canonical_inline_table(mapping: Mapping[str, Any]) -> InlineTable:
    """Build an inline table with the canonical ``{ key = value, ... }`` spacing.

    tomlkit's incremental inline-table edits leave non-canonical whitespace behind (double
    separators after a delete, no brace padding on fresh tables), which a later ``plxt format``
    would churn. Assembling the canonical text and parsing it yields the exact spacing the
    formatter emits.
    """
    if not mapping:
        return cast("InlineTable", tomlkit.value("{}"))
    inner = ", ".join(f"{item_key} = {_scalar_as_toml_text(item_value)}" for item_key, item_value in mapping.items())
    return cast("InlineTable", tomlkit.value("{ " + inner + " }"))


def _scalar_as_toml_text(value: Any) -> str:
    """One typed funnel over tomlkit's weakly-typed ``item(...).as_string()``."""
    return cast("str", tomlkit.item(value).as_string())  # pyright: ignore[reportUnknownMemberType]


def _canonicalize_mutated_inline_table(toml_doc: TOMLDocument, *, table_path: list[str], mutated_table: dict[str, Any]) -> None:
    """Re-emit a just-mutated inline table with canonical spacing, keeping its trailing comment.

    TOML forbids comments inside inline tables, so rebuilding one loses nothing; the line's
    trailing comment and indent live on the item's trivia and are transplanted onto the
    canonical replacement. Block tables are left untouched — their comments live between
    lines and in-place mutation already preserves them.
    """
    if not isinstance(mutated_table, InlineTable):
        return
    parent_table = _resolve_table(toml_doc, table_path=table_path[:-1])
    if parent_table is None:
        return
    canonical = _canonical_inline_table(mutated_table)
    canonical.trivia.indent = mutated_table.trivia.indent
    canonical.trivia.comment_ws = mutated_table.trivia.comment_ws
    canonical.trivia.comment = mutated_table.trivia.comment
    canonical.trivia.trail = mutated_table.trivia.trail
    parent_table[table_path[-1]] = canonical


def apply_fix_ops(toml_doc: TOMLDocument, *, ops: list[FixOp]) -> list[FixOpApplication]:
    """Apply each op to the DOM in place, returning one application report per op, in order.

    Idempotent: re-applying an already-applied op sets the same value / finds the key
    already gone, so the serialized bytes do not change.
    """
    applications: list[FixOpApplication] = []
    for fix_op in ops:
        applications.append(_apply_one_op(toml_doc, fix_op=fix_op))
    return applications


def _apply_one_op(toml_doc: TOMLDocument, *, fix_op: FixOp) -> FixOpApplication:
    table_path_str = ".".join(fix_op.table_path)
    match fix_op.kind:
        case FixOpKind.SET_KEY:
            if fix_op.key is None or fix_op.value is None:
                msg = f"set_key op on '{table_path_str}' requires both key and value — planner bug"
                raise PipelexUnexpectedError(msg)
            target_table = _resolve_table(toml_doc, table_path=fix_op.table_path)
            if target_table is None:
                return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"table '{table_path_str}' not found in document")
            target_table[fix_op.key] = _as_tomlkit_value(fix_op.value)
            _canonicalize_mutated_inline_table(toml_doc, table_path=fix_op.table_path, mutated_table=target_table)
            return FixOpApplication(op=fix_op, outcome=FixOpOutcome.APPLIED)
        case FixOpKind.DELETE_KEY:
            if fix_op.key is None:
                msg = f"delete_key op on '{table_path_str}' requires a key — planner bug"
                raise PipelexUnexpectedError(msg)
            target_table = _resolve_table(toml_doc, table_path=fix_op.table_path)
            if target_table is None:
                return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"table '{table_path_str}' not found in document")
            if fix_op.key not in target_table:
                return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"key '{fix_op.key}' not found in table '{table_path_str}'")
            del target_table[fix_op.key]
            _canonicalize_mutated_inline_table(toml_doc, table_path=fix_op.table_path, mutated_table=target_table)
            return FixOpApplication(op=fix_op, outcome=FixOpOutcome.APPLIED)
        case FixOpKind.DELETE_TABLE:
            if not fix_op.table_path:
                msg = "delete_table op requires a non-empty table_path — planner bug"
                raise PipelexUnexpectedError(msg)
            parent_table = _resolve_table(toml_doc, table_path=fix_op.table_path[:-1])
            table_key = fix_op.table_path[-1]
            # The final segment must itself be a table — a scalar there is a drifted target
            # (same guarded-skip contract _resolve_table enforces for every other segment).
            if parent_table is None or not isinstance(parent_table.get(table_key), dict):
                return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"table '{table_path_str}' not found in document")
            del parent_table[table_key]
            return FixOpApplication(op=fix_op, outcome=FixOpOutcome.APPLIED)
        case FixOpKind.RENAME_TABLE_KEY:
            # Position-preserving rename is phase-1 work (needed only by the strip-namespace
            # rule, which is gated on those mechanics landing clean). No spike planner emits it.
            msg = f"rename_table_key op on '{table_path_str}' is not supported yet"
            raise PipelexUnexpectedError(msg)
