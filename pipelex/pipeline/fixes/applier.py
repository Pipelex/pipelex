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

import copy
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import tomlkit
from pipelex_tools import format_mthds
from pydantic import BaseModel, ConfigDict, Field
from tomlkit import TOMLDocument
from tomlkit.container import Container, OutOfOrderTableProxy
from tomlkit.items import AbstractTable, AoT, Item, Table

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.suggested_fix import (
    WILDCARD_SEGMENT,
    DeleteKeyOp,
    DeleteTableOp,
    EnsureTableOp,
    FixOp,
    MoveKeyOp,
    RemapValueOp,
    RenameTableKeyOp,
    SetKeyOp,
    TomlValue,
)

if TYPE_CHECKING:
    # ``Diagnostic`` is a type-only TypedDict from the stub — declared in ``__all__`` but not a
    # runtime export of the compiled module, so it must not be imported at runtime.
    from pipelex_tools import Diagnostic


class FixOpOutcome(StrEnum):
    """What happened to one op during application.

    ``SKIPPED`` is benign and, under a migration's always-replay, overwhelmingly the common
    case: the target is gone or the change is already there. ``CONFLICT`` is not benign and
    must never travel inside ``SKIPPED`` — it means the change cannot be made without choosing
    on the user's behalf, typically because they hand-fixed part of the file themselves.
    Consumers classify on this enum and never by parsing ``detail``, which is presentation.
    """

    APPLIED = "applied"
    SKIPPED = "skipped"
    CONFLICT = "conflict"

    @property
    def did_apply(self) -> bool:
        match self:
            case FixOpOutcome.APPLIED:
                return True
            case FixOpOutcome.SKIPPED | FixOpOutcome.CONFLICT:
                return False

    @property
    def is_conflict(self) -> bool:
        """Whether the change could not be made without choosing on the user's behalf.

        A separate question from ``did_apply``: both a skip and a conflict left the document
        untouched, but only one of them is something a caller has to act on.
        """
        match self:
            case FixOpOutcome.CONFLICT:
                return True
            case FixOpOutcome.APPLIED | FixOpOutcome.SKIPPED:
                return False


class FixOpApplication(BaseModel):
    """Per-op application report: the op, whether it applied, and why not when skipped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: FixOp
    outcome: FixOpOutcome = Field(strict=False)
    detail: str | None = None


def _resolve_table(*, toml_doc: TOMLDocument, table_path: list[str]) -> dict[str, Any] | None:
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


def _rename_key_in_place(*, parent_table: dict[str, Any], key: str, new_key: str) -> None:
    """Rename ``key`` to ``new_key`` in a resolved table node, preserving position and comments.

    tomlkit exposes no public position-preserving rename; ``Container._replace`` is its own
    internal primitive (what ``__setitem__`` uses to re-home an existing key). It swaps the key in
    ``_body`` in place and re-renders the table header, so the renamed table keeps its position
    among siblings and its comments — a ``del`` + re-add would append it to the bottom of the
    parent (the old fixer's reordering bug). The golden byte-compare tests are the CI tripwire if
    a tomlkit bump ever changes this.

    ⚠ **A rename leaves the node's raw ``dict`` storage stale for a value that is not a Table.**
    ``_replace_at`` leaves the old key in the dict and only writes the new one into it inside its
    table branch, so everything tomlkit renders or looks up stays right (``dumps``, ``in``, ``[]``,
    ``.get()`` all read the authoritative body) while ``dict.__delitem__`` — which
    ``Container.remove`` calls — cannot find the new key. Addressing a renamed **scalar or
    inline-table** key again in the same DOM therefore raises ``KeyError`` from inside the library.
    The ``.mthds`` fix path is unaffected because it renames ``[pipe.*]`` tables, which take the
    branch tomlkit maintains; configuration migration re-reads the document between operations
    that applied, for exactly this reason. Both facts are pinned by
    ``tests/unit/pipelex/pipeline/fixes/test_fix_applier_rename_dom_consistency.py``, which is the
    tripwire if a tomlkit bump ever changes it.

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
                _replace_key_in_container(container=sub_table.value, key=key, new_key=new_key)
                renamed_in_any = True
        if not renamed_in_any:
            # The caller checked ``key in parent_table``, and the proxy's dict-facade is built from
            # exactly these sub-tables — reaching here means the facade and sub-tables disagree.
            msg = f"key '{key}' not found in any sub-table of the out-of-order table during rename — applier bug"
            raise PipelexUnexpectedError(msg)
        return
    if isinstance(parent_table, AbstractTable):
        _replace_key_in_container(container=parent_table.value, key=key, new_key=new_key)
        return
    if isinstance(parent_table, Container):
        _replace_key_in_container(container=parent_table, key=key, new_key=new_key)
        return
    msg = f"cannot rename key in unsupported tomlkit node type '{type(parent_table).__name__}' — applier bug"
    raise PipelexUnexpectedError(msg)


def _replace_key_in_container(*, container: Container, key: str, new_key: str) -> None:
    item = cast("Item", container[key])
    container._replace(key, new_key, item)  # pyright: ignore[reportPrivateUsage]
    _refresh_table_headers(item=item)


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


def apply_fix_ops(*, toml_doc: TOMLDocument, ops: Sequence[FixOp]) -> list[FixOpApplication]:
    """Apply each op to the DOM in place, returning one application report per op, in order.

    Idempotent: re-applying an already-applied op sets the same value / finds the key
    already gone, so the serialized bytes do not change.
    """
    applications: list[FixOpApplication] = []
    for fix_op in ops:
        applications.append(_apply_one_op(toml_doc=toml_doc, fix_op=fix_op))
    return applications


class _OpResult(NamedTuple):
    """One op's effect at one concrete table path, before wildcard expansions are folded."""

    outcome: FixOpOutcome
    detail: str | None = None


def _expand_table_paths(*, toml_doc: TOMLDocument, table_path: list[str]) -> list[list[str]]:
    """Resolve ``table_path`` into the concrete paths it addresses in this document.

    A path with no wildcard is itself, always — expansion never filters, so a path pointing at
    a table the document does not have still reaches its handler and is reported as a guarded
    skip there, exactly as before wildcards existed.

    A ``*`` segment expands over the table-valued keys present at that node, which is what
    "every entry of this open mapping" means for a file: the keys belong to the user, so the
    document is the only thing that can enumerate them. A wildcard over a node that is absent,
    or that holds no table-valued key, expands to nothing.
    """
    if WILDCARD_SEGMENT not in table_path:
        return [table_path]
    expanded_paths: list[list[str]] = [[]]
    for segment in table_path:
        if segment != WILDCARD_SEGMENT:
            expanded_paths = [[*path, segment] for path in expanded_paths]
            continue
        next_paths: list[list[str]] = []
        for path in expanded_paths:
            node = _resolve_table(toml_doc=toml_doc, table_path=path)
            if node is None:
                continue
            next_paths.extend([*path, key] for key, value in node.items() if isinstance(value, dict))
        expanded_paths = next_paths
    return expanded_paths


def _apply_one_op(*, toml_doc: TOMLDocument, fix_op: FixOp) -> FixOpApplication:
    """Apply one op at every concrete path it addresses, folded into a single report.

    An op is one step, and a conflicting step writes nothing — including a wildcard op whose
    conflict sits in the *last* matched entry. Every handler decides its own conflict before it
    writes, so a single path is atomic by construction; across several paths the op is first
    rehearsed on a copy of the document, and touches the real one only once no match conflicts.
    """
    concrete_paths = _expand_table_paths(toml_doc=toml_doc, table_path=fix_op.table_path)
    if not concrete_paths:
        detail = f"no table matches '{'.'.join(fix_op.table_path)}' in document"
        return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=detail)
    if len(concrete_paths) == 1:
        result = _apply_at_table_path(toml_doc=toml_doc, fix_op=fix_op, table_path=concrete_paths[0])
        return FixOpApplication(op=fix_op, outcome=result.outcome, detail=result.detail)
    rehearsal = copy.deepcopy(toml_doc)
    rehearsed = [_apply_at_table_path(toml_doc=rehearsal, fix_op=fix_op, table_path=path) for path in concrete_paths]
    if any(result.outcome is FixOpOutcome.CONFLICT for result in rehearsed):
        return _fold_wildcard_results(fix_op=fix_op, results=rehearsed)
    results = [_apply_at_table_path(toml_doc=toml_doc, fix_op=fix_op, table_path=path) for path in concrete_paths]
    return _fold_wildcard_results(fix_op=fix_op, results=results)


def _fold_wildcard_results(*, fix_op: FixOp, results: list[_OpResult]) -> FixOpApplication:
    """Reduce one wildcard op's per-entry results to the single report the caller sees.

    A conflict anywhere wins, because a conflict is the one outcome a caller must act on and
    burying it under a sibling entry's success would hide exactly what the outcome exists to
    surface. Otherwise any application makes the op applied, and only an op that did nothing
    anywhere is skipped.
    """
    conflicts = [result for result in results if result.outcome is FixOpOutcome.CONFLICT]
    if conflicts:
        return FixOpApplication(
            op=fix_op,
            outcome=FixOpOutcome.CONFLICT,
            detail=f"{len(conflicts)} of {len(results)} matched tables conflict — first: {conflicts[0].detail}",
        )
    applied_count = sum(1 for result in results if result.outcome.did_apply)
    if applied_count:
        return FixOpApplication(
            op=fix_op,
            outcome=FixOpOutcome.APPLIED,
            detail=f"applied in {applied_count} of {len(results)} matched tables",
        )
    return FixOpApplication(op=fix_op, outcome=FixOpOutcome.SKIPPED, detail=f"nothing to do in any of {len(results)} matched tables")


def _apply_at_table_path(*, toml_doc: TOMLDocument, fix_op: FixOp, table_path: list[str]) -> _OpResult:
    """Dispatch one op to its handler, at one already-expanded concrete table path.

    Matching on the op **type** rather than on its ``kind`` is what removes the shape checks
    this function used to open with: each variant of the union declares exactly the fields its
    handler reads, so "a set_key without a value" is a pydantic error at construction and can no
    longer reach the applier as a runtime "planner bug" raise.
    """
    table_path_str = ".".join(table_path)
    match fix_op:
        case SetKeyOp():
            target_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if target_table is None:
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            target_table[fix_op.key] = _as_tomlkit_value(fix_op.value)
            return _OpResult(FixOpOutcome.APPLIED)
        case EnsureTableOp():
            existing_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if existing_table is not None:
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' already exists")
            parent_table = _resolve_table(toml_doc=toml_doc, table_path=table_path[:-1])
            if parent_table is None:
                return _OpResult(FixOpOutcome.SKIPPED, f"parent of table '{table_path_str}' not found")
            table_key = table_path[-1]
            if table_key in parent_table:
                # The key is there but is not a table — the check above would have resolved it.
                # Creating the table would destroy whatever the user put there, so this is a
                # choice on their behalf, not an absence: a conflict, and not the "parent not
                # found" this branch used to report.
                return _OpResult(FixOpOutcome.CONFLICT, f"'{table_key}' is already present in '{'.'.join(table_path[:-1])}' and is not a table")
            parent_table[table_key] = tomlkit.inline_table()
            return _OpResult(FixOpOutcome.APPLIED)
        case DeleteKeyOp():
            target_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if target_table is None:
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            if fix_op.key not in target_table:
                return _OpResult(FixOpOutcome.SKIPPED, f"key '{fix_op.key}' not found in table '{table_path_str}'")
            del target_table[fix_op.key]
            return _OpResult(FixOpOutcome.APPLIED)
        case DeleteTableOp():
            parent_table = _resolve_table(toml_doc=toml_doc, table_path=table_path[:-1])
            table_key = table_path[-1]
            # The final segment must itself be a table — a scalar there is a drifted target
            # (same guarded-skip contract _resolve_table enforces for every other segment).
            if parent_table is None or not isinstance(parent_table.get(table_key), dict):
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            del parent_table[table_key]
            return _OpResult(FixOpOutcome.APPLIED)
        case RenameTableKeyOp():
            parent_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if parent_table is None or fix_op.key not in parent_table:
                return _OpResult(FixOpOutcome.SKIPPED, f"key '{fix_op.key}' not found in table '{table_path_str}'")
            if fix_op.new_key in parent_table:
                # Collision: the bare name is already taken by a separate declaration — renaming
                # would clobber it. The raise-site guard suppresses this case for `.mthds` fixes,
                # but the applier stays defensive (a stale fix from a prior loop iteration, or a
                # user who hand-fixed half of a migration, could reach here).
                return _OpResult(FixOpOutcome.CONFLICT, f"cannot rename to '{fix_op.new_key}': already present in table '{table_path_str}'")
            _rename_key_in_place(parent_table=parent_table, key=fix_op.key, new_key=fix_op.new_key)
            return _OpResult(FixOpOutcome.APPLIED)
        case MoveKeyOp():
            return _apply_move_key(toml_doc=toml_doc, fix_op=fix_op, table_path=table_path)
        case RemapValueOp():
            target_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if target_table is None:
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            if fix_op.key == WILDCARD_SEGMENT:
                return _remap_every_value(target_table=target_table, mapping=fix_op.mapping, table_path_str=table_path_str)
            if fix_op.key not in target_table:
                return _OpResult(FixOpOutcome.SKIPPED, f"key '{fix_op.key}' not found in table '{table_path_str}'")
            return _remap_one_value(target_table=target_table, key=fix_op.key, mapping=fix_op.mapping, table_path_str=table_path_str)


def _remap_one_value(*, target_table: dict[str, Any], key: str, mapping: dict[str, str], table_path_str: str) -> _OpResult:
    """Rewrite one key's value through the mapping, skipping anything the mapping does not name."""
    current_value = target_table[key]
    if not isinstance(current_value, str):
        return _OpResult(FixOpOutcome.SKIPPED, f"value of '{table_path_str}.{key}' is not a string")
    new_value = mapping.get(str(current_value))
    if new_value is None:
        # The current value is deliberately not named: a report must never echo a value
        # read from a user's file (docs/migration-ledger.md, "What the engine reports").
        return _OpResult(FixOpOutcome.SKIPPED, f"value of '{table_path_str}.{key}' is not in this operation's mapping")
    target_table[key] = new_value
    return _OpResult(FixOpOutcome.APPLIED)


def _remap_every_value(*, target_table: dict[str, Any], mapping: dict[str, str], table_path_str: str) -> _OpResult:
    """Rewrite every value of the addressed table through the mapping — the ``*`` key.

    This is the "each of these" reading the wildcard already has in a ``table_path``, applied to
    keys instead of to tables, and it is what a mapping from the user's own keys to an enumerated
    value needs: the keys are the user's, so only the document can enumerate them, and no fixed
    ``key`` reaches them. A remap never collides, so folding many entries into one outcome needs
    no conflict rule: any rewrite makes the operation applied, none makes it skipped.
    """
    remapped = 0
    for key in list(target_table):
        if _remap_one_value(target_table=target_table, key=key, mapping=mapping, table_path_str=table_path_str).outcome.did_apply:
            remapped += 1
    if not remapped:
        return _OpResult(FixOpOutcome.SKIPPED, f"no value in '{table_path_str}' is one this operation's mapping names")
    return _OpResult(FixOpOutcome.APPLIED, f"remapped {remapped} of {len(target_table)} values in '{table_path_str}'")


def _refresh_table_headers(*, item: Any) -> None:
    """Make every table beneath a renamed or moved ``item`` re-render its header under its new path.

    tomlkit caches each table's rendered header in ``Table.display_name`` and, after a re-key,
    invalidates that cache by walking ``Table.values()`` — the merged dict facade, which yields
    one item per key. A table written in several chunks (``[a.b]`` … ``[a.c]`` … ``[a.b.d]``) is
    several ``Table`` items under one key, so only the first chunk is visited and the others keep
    rendering under the old name: the file comes out split between two tables with an
    ``applied`` verdict. Walking the *body* instead reaches every chunk, so clearing the cache
    here is what lets a rename or move come out whole for any layout the parser accepts.
    """
    if isinstance(item, OutOfOrderTableProxy):
        for chunk in item._tables:  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            _refresh_table_headers(item=chunk)
        return
    if isinstance(item, Table):
        item.display_name = None
        _refresh_table_headers(item=item.value)
        return
    if isinstance(item, AoT):
        for element in item.body:
            _refresh_table_headers(item=element)
        return
    if isinstance(item, Container):
        for _, child in item.body:
            _refresh_table_headers(item=child)


def _apply_move_key(*, toml_doc: TOMLDocument, fix_op: MoveKeyOp, table_path: list[str]) -> _OpResult:
    """Relocate one key, creating whatever destination parents are missing.

    Order matters and is the whole reason this is not inline: everything that can refuse the
    move is decided **before** anything is written, so a conflicting move leaves the document
    byte-identical rather than seeded with the empty parent tables it was about to fill.
    """
    table_path_str = ".".join(table_path)
    destination_path_str = ".".join(fix_op.new_table_path)
    source_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
    if source_table is None or fix_op.key not in source_table:
        return _OpResult(FixOpOutcome.SKIPPED, f"key '{fix_op.key}' not found in table '{table_path_str}'")

    blocking_segment = _first_non_table_segment(toml_doc=toml_doc, table_path=fix_op.new_table_path)
    if blocking_segment is not None:
        return _OpResult(
            FixOpOutcome.CONFLICT, f"destination '{destination_path_str}' is blocked: '{blocking_segment}' is present and is not a table"
        )
    existing_destination = _resolve_table(toml_doc=toml_doc, table_path=fix_op.new_table_path)
    if existing_destination is not None and fix_op.new_key in existing_destination:
        return _OpResult(FixOpOutcome.CONFLICT, f"cannot move to '{destination_path_str}.{fix_op.new_key}': already present")

    moved_value = cast("Item", source_table[fix_op.key])
    del source_table[fix_op.key]
    destination_table = _create_block_table_path(toml_doc=toml_doc, table_path=fix_op.new_table_path)
    destination_table[fix_op.new_key] = moved_value
    _refresh_table_headers(item=moved_value)
    return _OpResult(FixOpOutcome.APPLIED)


def _first_non_table_segment(*, toml_doc: TOMLDocument, table_path: list[str]) -> str | None:
    """The first segment of ``table_path`` that exists and is not a table, if there is one.

    One walk answers the whole question because absence is terminal: once a segment is missing,
    every deeper segment is missing too and the rest of the path is free to be created.
    """
    node = cast("dict[str, Any]", toml_doc)
    for segment in table_path:
        candidate = node.get(segment)
        if candidate is None:
            return None
        if not isinstance(candidate, dict):
            return segment
        node = cast("dict[str, Any]", candidate)
    return None


def _create_block_table_path(*, toml_doc: TOMLDocument, table_path: list[str]) -> dict[str, Any]:
    """Walk ``table_path``, creating missing segments as block tables, and return the leaf node.

    Block tables rather than inline ones, because this creates a *section* of a configuration
    file — a destination that will hold moved keys and be read by a human. Callers must have
    ruled out a non-table segment first; this function would silently overwrite one.
    """
    node = cast("dict[str, Any]", toml_doc)
    for segment in table_path:
        if not isinstance(node.get(segment), dict):
            node[segment] = tomlkit.table()
        node = cast("dict[str, Any]", node[segment])
    return node
