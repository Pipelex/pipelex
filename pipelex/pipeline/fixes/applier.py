"""Fix applier — applies ``FixOp`` patch ops to a tomlkit DOM, then renders canonical MTHDS.

Two clearly-separated steps, because they preserve different things — do not conflate them:

- ``apply_fix_ops`` mutates the tomlkit DOM **in place**, never rebuilding containers, so at the
  DOM level tomlkit keeps the comments, ordering, and table style of untouched content (and of
  the patched line itself) by construction. A caller that wants the mutated-but-unformatted DOM
  stops here.
- ``serialize_and_format`` then serializes the whole DOM and hands it to the MTHDS formatter
  (``pipelex_tools.format_mthds``) for the one canonical style. This is a **whole-file** reflow:
  the returned text is canonical MTHDS, not a surgical diff — spacing and column alignment of
  *untouched* tables is normalized too (a no-op on already-formatted files, which is the norm,
  since MTHDS is formatted on save + CI-enforced). This is the intended output philosophy for a
  file-rewriting fix tool; it is emphatically not byte-level preservation of untouched lines.

Guarded application: an op only applies when its target table path exists in the DOM. This
protects against errors raised on elaborated/synthetic constructs (a synthesized sequence has no
TOML to patch) and against ops targeting a different file than the one being patched — a skipped
op is reported, never raised.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

import tomlkit
from pipelex_tools import format_mthds
from pydantic import BaseModel, ConfigDict, Field
from tomlkit import TOMLDocument
from tomlkit.container import Container, OutOfOrderTableProxy
from tomlkit.items import AbstractTable, Item

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.suggested_fix import FixOp, FixOpKind, TomlValue

if TYPE_CHECKING:
    # ``Diagnostic`` is a type-only TypedDict from the stub — declared in ``__all__`` but not a
    # runtime export of the compiled module, so it must not be imported at runtime.
    from pipelex_tools import Diagnostic


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


def _rename_key_in_place(parent_table: dict[str, Any], *, key: str, new_key: str) -> None:
    """Rename ``key`` to ``new_key`` in a resolved table node, preserving position and comments.

    tomlkit exposes no public position-preserving rename; ``Container._replace`` is its own
    internal primitive (what ``__setitem__`` uses to re-home an existing key). It swaps the key in
    ``_body`` in place and re-renders the table header, so the renamed table keeps its position
    among siblings and its comments — a ``del`` + re-add would append it to the bottom of the
    parent (the old fixer's reordering bug). The golden byte-compare tests are the CI tripwire if
    a tomlkit bump ever changes this.

    ``_resolve_table`` hands back one of three dict-like shapes, each with its own route to the
    ``Container`` that owns the key:

    - ``OutOfOrderTableProxy`` — ``[pipe.*]`` sections interleaved with other tables: the keys
      live in the proxy's underlying sub-tables, so rename inside **every** one holding ``key``;
    - ``AbstractTable`` — a regular ``Table`` or an inline ``pipe = {...}``: its ``.value``;
    - the root ``TOMLDocument``, itself a ``Container``.
    """
    if isinstance(parent_table, OutOfOrderTableProxy):
        # The same dotted key can appear in MORE THAN ONE sub-table: a pipe whose header
        # ``[pipe."d.x"]`` and whose block ``[pipe."d.x".inputs]`` land in different out-of-order
        # chunks (split by an intervening ``[concept]`` etc.) both carry the key ``d.x``. Renaming
        # only the first would leave the other chunk under the old dotted name — orphaning the
        # pipe's nested content in a phantom, still-invalid key. Rename in every chunk holding it.
        renamed_in_any = False
        for sub_table in parent_table._tables:  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            if key in sub_table:
                _replace_key_in_container(sub_table.value, key=key, new_key=new_key)
                renamed_in_any = True
        if not renamed_in_any:
            # The caller checked ``key in parent_table``, and the proxy's dict-facade is built from
            # exactly these sub-tables — reaching here means the facade and sub-tables disagree.
            msg = f"key '{key}' not found in any sub-table of the out-of-order table during rename — applier bug"
            raise PipelexUnexpectedError(msg)
        return
    if isinstance(parent_table, AbstractTable):
        _replace_key_in_container(parent_table.value, key=key, new_key=new_key)
        return
    if isinstance(parent_table, Container):
        _replace_key_in_container(parent_table, key=key, new_key=new_key)
        return
    msg = f"cannot rename key in unsupported tomlkit node type '{type(parent_table).__name__}' — applier bug"
    raise PipelexUnexpectedError(msg)


def _replace_key_in_container(container: Container, *, key: str, new_key: str) -> None:
    container._replace(key, new_key, cast("Item", container[key]))  # pyright: ignore[reportPrivateUsage]


def _as_tomlkit_value(value: TomlValue | None) -> Any:
    """Convert a mapping value to an inline table (`inputs = { ... }`, the dominant authoring
    form), so a freshly-created mapping stays attached to its pipe rather than being emitted as
    a detached ``[pipe.x.inputs]`` block table at the end of the file (what a plain dict assign
    yields). tomlkit owns key quoting and per-value rendering; canonical spacing is the
    formatter's job in ``serialize_and_format``. Scalars pass through — tomlkit wraps them on
    assignment.
    """
    if isinstance(value, dict):
        inline = tomlkit.inline_table()
        for item_key, item_value in value.items():
            inline[item_key] = item_value
        return inline
    return value


def serialize_and_format(toml_doc: TOMLDocument) -> str:
    """Serialize the mutated DOM and return its canonical MTHDS text.

    The applier mutates in place and leaves formatting alone; the single source of canonical
    style is ``pipelex_tools.format_mthds`` (the same ``taplo``/MTHDS engine the ``plxt`` CLI
    runs on save), which reflows inline-table and array spacing to the canonical form and is a
    no-op on already-canonical files (the norm — MTHDS is formatted on save + CI-enforced). A
    ``kind="syntax"`` diagnostic means the applier emitted malformed TOML — a planner/applier
    bug, never something to write out — so it is raised, not swallowed.
    """
    dumped: str = tomlkit.dumps(toml_doc)  # pyright: ignore[reportUnknownMemberType]
    result = format_mthds(dumped)
    syntax_diagnostics = [diagnostic for diagnostic in result["diagnostics"] if diagnostic["kind"] == "syntax"]
    if syntax_diagnostics:
        reported = "; ".join(_render_syntax_diagnostic(diagnostic) for diagnostic in syntax_diagnostics)
        msg = f"fix applier produced malformed TOML (formatter reported: {reported}) — planner/applier bug"
        raise PipelexUnexpectedError(msg)
    return result["formatted"]


def _render_syntax_diagnostic(diagnostic: "Diagnostic") -> str:
    """One formatter syntax diagnostic as ``message (line L:C)``, keeping the position it carries
    so a planner/applier bug is debuggable from the raised message alone.
    """
    diagnostic_range = diagnostic["range"]
    if diagnostic_range is None:
        return diagnostic["message"]
    return f"{diagnostic['message']} (line {diagnostic_range['start_line']}:{diagnostic_range['start_col']})"


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
            if fix_op.key is None or fix_op.new_key is None:
                msg = f"rename_table_key op on '{table_path_str}' requires both key and new_key — planner bug"
                raise PipelexUnexpectedError(msg)
            parent_table = _resolve_table(toml_doc, table_path=fix_op.table_path)
            if parent_table is None or fix_op.key not in parent_table:
                return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"key '{fix_op.key}' not found in table '{table_path_str}'")
            if fix_op.new_key in parent_table:
                # Collision: the bare name is already taken by a separate declaration — renaming
                # would clobber it. The raise-site guard suppresses this case, but the applier
                # stays defensive (a stale fix from a prior loop iteration could reach here).
                return FixOpApplication(
                    op=fix_op,
                    outcome=FixOpOutcome.SKIPPED,
                    detail=f"cannot rename to '{fix_op.new_key}': already present in table '{table_path_str}'",
                )
            _rename_key_in_place(parent_table, key=fix_op.key, new_key=fix_op.new_key)
            return FixOpApplication(op=fix_op, outcome=FixOpOutcome.APPLIED)
