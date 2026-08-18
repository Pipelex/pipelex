"""Fix applier — applies ``FixOp`` patch ops to a tomlkit DOM, then renders canonical MTHDS.

Two clearly-separated steps, because they preserve different things — do not conflate them:

- ``apply_fix_ops`` mutates the tomlkit DOM **in place**, never rebuilding containers, so at the
  DOM level tomlkit keeps the comments, ordering, and table style of untouched content (and of
  the patched line itself) by construction. What tomlkit does *not* do on its own is keep a
  comment on the item it introduces when that item moves or goes — the "Comment fidelity"
  helpers below do that, see their heading. A caller that wants the mutated-but-unformatted DOM
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
from tomlkit.items import AbstractTable, AoT, Comment, Item, Key, Null, SingleKey, Table, Whitespace

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

    tomlkit exposes no public position-preserving rename, so ``_replace_key_in_container`` renames
    the container's body entries in place: the key keeps its slot among its siblings and its
    comments, where a ``del`` + re-add would append it to the bottom of the parent (the old
    fixer's reordering bug). The golden byte-compare tests are the CI tripwire if a tomlkit bump
    ever changes what that body looks like.

    ⚠ **A rename leaves the node's raw ``dict`` storage stale for a value that is not a Table.**
    A ``Table`` and the ``Container`` inside it are two dict-like objects each holding their own
    copy of the key set, and a rename reaching the container has no way to reach the parent
    table's copy. So everything tomlkit renders or looks up stays right (``dumps``, ``in``, ``[]``,
    ``.get()`` all read the authoritative body) while ``dict.__delitem__`` — which
    ``Container.remove`` calls — cannot find the new key. Addressing a renamed **scalar or
    inline-table** key again in the same DOM therefore raises ``KeyError`` from inside the library.
    The ``.mthds`` fix path is unaffected because it renames ``[pipe.*]`` tables, which take the
    branch tomlkit does keep in step; configuration migration re-reads the document between
    operations that applied, for its own reasons, and is unaffected too. Both facts are pinned by
    ``tests/unit/pipelex/pipeline/fixes/test_fix_applier_rename_dom_consistency.py``, which is the
    tripwire if this is ever repaired across every facade.

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
    """Rename one key of a container in place — every chunk of it, and nothing beyond the name.

    A rename changes a name. tomlkit's own re-key primitive, ``Container._replace``, does three
    further things on the way, and each of them is a defect on a **dotted** key — the ordinary way
    to write a one-line entry of a section (``package_log_levels.pipelex = "INFO"``), and one no
    formatter rewrites into anything else:

    - **Dotted-ness is dropped.** It is not a property of the name but of how the line was
      written: the key owns a super-table and carries a flag the parser sets, and the renderer
      reads that flag to choose between a dotted assignment and a ``[a.k]`` header. Rebuilt as a
      plain key, ``k.x = 1`` came back out as a header — and a header **absorbs every scalar that
      follows it in the same table**, so a neighbouring ``m = 3`` silently became ``a.kk.m``, with
      an ``applied`` verdict and nothing said. Renamed at an inner segment the chain re-rendered
      at the document *root*, taking the whole subtree out of the table it lived in.
    - **Chunks are collapsed.** A key written as several dotted lines (``k.x = 1`` then
      ``k.y = 2``) is several body entries under one key, and the primitive keeps the first, nulls
      the rest, and rebuilds one merged value from the container's dict facade — which for this
      shape holds only the last chunk.
    - **A blank line is injected.** The primitive appends a cosmetic newline to a replaced table.
      That is right for a block table it is about to re-home, and wrong for an assignment.

    Refusing the layout with a ``CONFLICT`` was the alternative the migration plan named, and it
    is the wrong trade: a rename has exactly one correct answer on a dotted key (``kk.x = 1``),
    and refusing would strand a configuration migration's table renames on any file that happens
    to be written this way. This is a rendering defect with a root cause, like the stale
    ``display_name`` on a table split across chunks, and it is fixed at the root for the same reason.

    Renaming the body entries directly is also what keeps position and comments — the property
    ``_replace`` was reached for in the first place — since nothing is removed or re-appended.
    """
    renamed_positions = [
        (position, body_key) for position, (body_key, _) in enumerate(container.body) if body_key is not None and body_key.key == key
    ]
    if not renamed_positions:
        # ``_rename_key_in_place`` checked membership through the dict facade; an empty body means
        # the facade and the body disagree, which is a bug here rather than a document to migrate.
        msg = f"key '{key}' is in the container's facade but in none of its body entries during rename — applier bug"
        raise PipelexUnexpectedError(msg)

    for position, body_key in renamed_positions:
        _, body_item = container.body[position]
        container.body[position] = (_renamed_key(previous=body_key, new_key=new_key), body_item)
        _refresh_table_headers(item=body_item)

    # The side indexes hold one entry per name, and tomlkit keeps the last chunk appended.
    last_position, last_body_key = renamed_positions[-1]
    _rehome_key_indexes(
        container=container,
        key=key,
        renamed=_renamed_key(previous=last_body_key, new_key=new_key),
        item=container.body[last_position][1],
    )


def _renamed_key(*, previous: Key, new_key: str) -> SingleKey:
    """A fresh key under the new name, carrying forward the one property a rename must not lose.

    Everything else — quoting, separator — is left to tomlkit's own construction, so renaming an
    ordinary key yields exactly the key the library would have built for it.
    """
    renamed = SingleKey(new_key)
    if previous.is_dotted():
        # There is no public way to say "dotted": the flag is private, and tomlkit's own parser
        # sets it exactly this way in ``Container._handle_dotted_key``.
        renamed._dotted = True  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    return renamed


def _rehome_key_indexes(*, container: Container, key: str, renamed: SingleKey, item: Item) -> None:
    """Move a renamed key in the two side indexes a ``Container`` carries beside its body.

    The body is what tomlkit renders from; beside it sit a private map from key to body position,
    which the public accessors read, and the raw ``dict`` storage a ``Container`` inherits, which
    ``len()``, iteration and ``.get()`` read.

    Both are updated exactly as ``Container._replace_at`` updates them, **including its asymmetry**
    — the raw storage gets the new name back only for a ``Table``. That asymmetry is the known
    staleness ``_rename_key_in_place`` documents and ``test_fix_applier_rename_dom_consistency.py``
    pins, and it is deliberately not repaired here: the storage this function can reach is the
    container's, while a nested rename's stale facade is the parent ``Table``'s own — a different
    dict, holding items rather than values. Repairing one of the two would move the inconsistency
    rather than end it, so the whole set of facades is one deliberate pass, not a rider on this one.
    """
    container._map[renamed] = container._map.pop(SingleKey(key))  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    # ``dict`` explicitly on both lines — a ``Container`` is a ``MutableMapping`` *and* a ``dict``,
    # so its own ``pop`` and ``[] =`` route through ``Container.__getitem__`` / ``__delitem__``,
    # which read and rewrite the very body this function has just finished renaming. The stubs
    # type the inherited members as ``dict[Unknown, Unknown]``, hence the narrow ignores.
    dict.pop(container, key, None)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if isinstance(item, Table):
        # The raw storage holds one entry per name, and for a key written as several chunks
        # tomlkit keeps the last one appended — which is the item this is handed.
        dict.__setitem__(container, renamed.key, item.value)  # noqa: PLC2801 # pyright: ignore[reportUnknownMemberType]


# --- Comment fidelity: the trivia that introduces an item goes where the item goes -----------------
#
# tomlkit keeps own-line comments and blank lines as keyless body entries (``Comment``,
# ``Whitespace``), positioned wherever the parser met them: a comment above a key sits before that
# key in the same container, and a banner written above a ``[table]`` header sits at the *tail of
# the previous table in document order* — inside its deepest last container — because everything up
# to the next header belongs to the table being parsed. Nothing ties either run to the item it
# visibly introduces, so a plain ``del`` + re-add of a table leaves its banner behind (now labelling
# whatever followed) and carries the *next* table's banner away inside the moved body; appending
# under an existing table lands *after* that table's trailing banner, stealing it the same way.
#
# The rule the helpers below implement is the one a reader applies: **the last block of own-line
# comments before an item, with the blank line above it and anything below it, introduces that
# item.** Earlier blocks in the same run — a file preamble, a note closing the previous section —
# stay where they are; a run holding no comment at all is spacing and travels whole. A moved item
# takes its introduction along and leaves its trailing run, the next item's introduction, where it
# was; a deleted item drops its introduction and keeps its trailing run in place; an item inserted at
# the end of a container lands before that container's trailing run, never after it. Trivia is
# always put back where the parser would have put it — a previous table's deepest tail rather than
# a super-table's own body — so no implicit ``[parent]`` header starts rendering because a comment
# now sits inside it. Inline tables are left alone: their whitespace entries are layout.


class _TriviaRun(NamedTuple):
    """The positions of a run of comment/blank-line entries in one container's body, ascending."""

    container: Container
    positions: list[int]

    def items(self) -> list[Item]:
        return [self.container.body[position][1] for position in self.positions]


class _Slot(NamedTuple):
    """One key's place in the document: the concrete container holding it and its body positions.

    ``owner`` is the table whose ``.value`` the container is — one chunk of it, for a key of an
    out-of-order table — and ``None`` at the document root.
    """

    container: Container
    positions: list[int]
    owner: Table | None

    @property
    def first(self) -> int:
        return self.positions[0]

    @property
    def last(self) -> int:
        return self.positions[-1]


def _is_trivia(*, item: Item) -> bool:
    return isinstance(item, (Comment, Whitespace))


def _last_container(*, item: Item) -> Container | None:
    """The container whose tail is the tail of ``item`` in document order, or ``None`` for a leaf.

    Only block tables and arrays of tables extend across lines; an inline table renders on its
    key's line and never owns any trailing trivia.
    """
    if isinstance(item, Table):
        return item.value
    if isinstance(item, AoT):
        return item.body[-1].value if item.body else None
    if isinstance(item, OutOfOrderTableProxy):
        return item._tables[-1].value  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    return None


def _renders_header(*, table: Table, key: Key | None) -> bool:
    """Whether tomlkit writes a ``[header]`` line for ``table``, stored under ``key`` — mirrors ``Container._render_table``.

    An implicit super table has none: ``[a.b]`` written without ``[a]``, or a dotted assignment
    ``a.b = 1`` whose owning key is dotted, so its scalars render on their own lines. Trivia sitting
    above such a table's first entry is, to a reader, above the first entry's own header.
    """
    if not table.is_super_table():
        return True
    if key is not None and key.is_dotted():
        return False
    body = table.value.body
    if any(not isinstance(item, (Table, AoT, Whitespace, Null)) for _, item in body):
        return True
    return any(body_key is not None and body_key.is_dotted() for body_key, item in body if isinstance(item, Table))


def _key_slot(*, parent_table: dict[str, Any], key: str) -> _Slot:
    """Where ``key`` is stored beneath ``parent_table``.

    A key written as several dotted chunks has several positions in one container, and a key of an
    out-of-order table can sit in any of the proxy's chunks: the chunk holding the key's first
    position is the one taken, since that is where the key's introduction is.
    """
    candidates: list[tuple[Container, Table | None]]
    if isinstance(parent_table, OutOfOrderTableProxy):
        candidates = [(sub_table.value, sub_table) for sub_table in parent_table._tables if key in sub_table]  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    elif isinstance(parent_table, Table):
        candidates = [(parent_table.value, parent_table)]
    elif isinstance(parent_table, Container):
        candidates = [(parent_table, None)]
    else:
        msg = f"cannot locate key '{key}' in unsupported tomlkit node type '{type(parent_table).__name__}' — applier bug"
        raise PipelexUnexpectedError(msg)
    for container, owner in candidates:
        position = container._map.get(SingleKey(key))  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        if position is None:
            continue
        positions = sorted(position) if isinstance(position, tuple) else [position]
        return _Slot(container=container, positions=positions, owner=owner)
    msg = f"key '{key}' is in the parent's facade but in none of its body entries — applier bug"
    raise PipelexUnexpectedError(msg)


def _slot_chain(*, toml_doc: TOMLDocument, path: list[str]) -> list[_Slot]:
    """The slot of every segment of ``path``, root first — the ancestry a climb through implicit parents needs.

    Stops short at an inline table: nothing beneath one carries introductions.
    """
    chain: list[_Slot] = []
    node = cast("dict[str, Any]", toml_doc)
    for segment in path:
        if not _carries_trivia(parent_table=node):
            break
        chain.append(_key_slot(parent_table=node, key=segment))
        node = cast("dict[str, Any]", node[segment])
    return chain


def _carries_trivia(*, parent_table: dict[str, Any]) -> bool:
    """Whether the parent is a container whose comments and blank lines are introductions.

    An inline table's whitespace entries are its layout, so the fidelity rule stays out of it.
    """
    return isinstance(parent_table, (Table, Container, OutOfOrderTableProxy))


def _run_before(*, container: Container, index: int) -> _TriviaRun:
    """The trivia run right before the body entry at ``index`` — possibly inside a previous table.

    Walks back over comments and blank lines (``Null`` placeholders left by an earlier removal are
    transparent). When nothing was collected and the entry before is a table, the run is that
    table's trailing run in document order, so the walk descends into its deepest last container.
    Trivia found at this level wins over a deeper tail: it is what the parser put here.
    """
    positions: list[int] = []
    for position in range(index - 1, -1, -1):
        _, item = container.body[position]
        if isinstance(item, Null):
            continue
        if _is_trivia(item=item):
            positions.insert(0, position)
            continue
        if not positions:
            deeper = _last_container(item=item)
            if deeper is not None:
                return _trailing_run(container=deeper)
        break
    return _TriviaRun(container=container, positions=positions)


def _run_after(*, container: Container, index: int) -> _TriviaRun:
    """The trivia run right after the body entry at ``index``, at this level only."""
    positions: list[int] = []
    for position in range(index + 1, len(container.body)):
        _, item = container.body[position]
        if isinstance(item, Null):
            continue
        if not _is_trivia(item=item):
            break
        positions.append(position)
    return _TriviaRun(container=container, positions=positions)


def _first_entry_after(*, container: Container, index: int) -> Item | None:
    """The first body entry after ``index`` that is neither a ``Null`` placeholder nor trivia."""
    for position in range(index + 1, len(container.body)):
        _, item = container.body[position]
        if isinstance(item, Null) or _is_trivia(item=item):
            continue
        return item
    return None


def _trailing_run(*, container: Container) -> _TriviaRun:
    """The trivia run at the tail of ``container`` in document order — its own, or its last table's."""
    return _run_before(container=container, index=len(container.body))


def _introduction(*, run: _TriviaRun, at_document_start: bool = False) -> _TriviaRun:
    """The part of a run that introduces what follows it: the last comment block, its leading blank line, and what trails it.

    A run with no comment is spacing and is taken whole. Earlier comment blocks stay put — a file
    preamble above the first section's banner, or a closing note under the previous section. At the
    very top of the document, a *lone* comment block that a blank line separates from what follows
    is the file's preamble and stays too: only the blank line after it travels.
    """
    items = run.items()
    last_comment = max((index for index, item in enumerate(items) if isinstance(item, Comment)), default=None)
    if last_comment is None:
        return run
    start = last_comment
    while start > 0 and isinstance(items[start - 1], Comment):
        start -= 1
    is_lone_block = not any(isinstance(item, Comment) for item in items[:start])
    is_set_apart = last_comment + 1 < len(items) and isinstance(items[last_comment + 1], Whitespace)
    if at_document_start and is_lone_block and is_set_apart:
        return _TriviaRun(container=run.container, positions=run.positions[last_comment + 1 :])
    if start > 0 and isinstance(items[start - 1], Whitespace):
        start -= 1
    return _TriviaRun(container=run.container, positions=run.positions[start:])


def _at_document_start(*, run: _TriviaRun) -> bool:
    """Whether the run is the first thing in the file — only a root-level run can be."""
    if not isinstance(run.container, TOMLDocument):
        return False
    return not run.positions or _is_first_entry(container=run.container, index=run.positions[0])


def _is_first_entry(*, container: Container, index: int) -> bool:
    return all(isinstance(item, Null) for _, item in container.body[:index])


def _owner_position(*, chain: list[_Slot]) -> int | None:
    """Where the last link's owner sits in its parent's container — ``None`` at the root, or once it is gone.

    Gone happens: deleting the last key of one chunk of an out-of-order table makes tomlkit drop the
    emptied chunk from the parent, leaving a ``Null`` where the chunk was.
    """
    if len(chain) < 2:
        return None
    owner = chain[-1].owner
    parent_container = chain[-2].container
    for position in chain[-2].positions:
        if parent_container.body[position][1] is owner:
            return position
    return None


def _owner_key(*, chain: list[_Slot]) -> Key | None:
    """The key the last link's owner is stored under in its parent — ``None`` at the root, or once it is gone."""
    position = _owner_position(chain=chain)
    if position is None:
        return None
    return chain[-2].container.body[position][0]


def _implicit_owner_position(*, chain: list[_Slot]) -> int | None:
    """Where the last link's owner sits in its own parent's container, when that owner renders no header.

    That is the one situation in which the entries of a table are, to a reader, entries of whatever
    encloses it: the trivia above the owner introduces the owner's first entry, and trivia meant for
    the owner's first entry belongs above the owner. ``None`` when the owner writes a header (or is
    the document root), or when the chain does not reach the parent.
    """
    if len(chain) < 2:
        return None
    owner = chain[-1].owner
    if owner is None or _renders_header(table=owner, key=_owner_key(chain=chain)):
        return None
    position = _owner_position(chain=chain)
    if position is None:
        msg = "an out-of-order chunk is not among its parent's body positions — applier bug"
        raise PipelexUnexpectedError(msg)
    return position


def _introduction_of_slot(*, chain: list[_Slot]) -> _TriviaRun:
    """The introduction of the key at the end of ``chain``, climbing through implicit parents.

    A key that is the first entry of a table with no rendered header — ``[runtime.storage]`` at the
    top of a file that never writes ``[runtime]`` — is introduced by whatever sits above the parent.
    """
    slot = chain[-1]
    run = _run_before(container=slot.container, index=slot.first)
    if run.positions or not _is_first_entry(container=slot.container, index=slot.first):
        return _introduction(run=run, at_document_start=_at_document_start(run=run))
    owner_position = _implicit_owner_position(chain=chain)
    if owner_position is None:
        return _introduction(run=run, at_document_start=_at_document_start(run=run))
    return _introduction_of_slot(chain=[*chain[:-2], chain[-2]._replace(positions=[owner_position])])


def _shift_map(*, container: Container, from_index: int, delta: int) -> None:
    """Keep the container's key→position index in step with a body insert or removal at ``from_index``."""
    key_map = container._map  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    for map_key, position in list(key_map.items()):
        if isinstance(position, tuple):
            key_map[map_key] = tuple(chunk + delta if chunk >= from_index else chunk for chunk in position)
        elif position >= from_index:
            key_map[map_key] = position + delta


def _detach_run(*, run: _TriviaRun) -> list[Item]:
    """Remove the run's entries from their container's body, returning them in document order."""
    detached: list[Item] = []
    for position in reversed(run.positions):
        _, item = run.container.body.pop(position)
        detached.insert(0, item)
        _shift_map(container=run.container, from_index=position, delta=-1)
    return detached


def _insert_trivia_at(*, container: Container, index: int, items: Sequence[Item]) -> None:
    for offset, item in enumerate(items):
        container.body.insert(index + offset, (None, item))
    if items:
        _shift_map(container=container, from_index=index, delta=len(items))


def _tail_slot(*, container: Container) -> tuple[Container, int]:
    """Where an entry appended to ``container`` lands last in document order: after its last table's body."""
    for position in range(len(container.body) - 1, -1, -1):
        _, item = container.body[position]
        if isinstance(item, Null):
            continue
        deeper = _last_container(item=item)
        if deeper is not None:
            return _tail_slot(container=deeper)
        break
    return container, len(container.body)


def _insert_before(*, chain: list[_Slot], index: int, items: Sequence[Item]) -> None:
    """Insert trivia so that it renders right before body entry ``index`` of the last chain link's container.

    Put where the parser would have put it: at the tail of the previous table when there is one,
    above an implicit parent when the entry is the first of a table with no rendered header, and at
    this level otherwise.
    """
    if not items:
        return
    slot = chain[-1]
    for position in range(index - 1, -1, -1):
        _, item = slot.container.body[position]
        if isinstance(item, Null):
            continue
        deeper = _last_container(item=item)
        if deeper is None:
            _insert_trivia_at(container=slot.container, index=index, items=items)
            return
        tail_container, tail_index = _tail_slot(container=deeper)
        _insert_trivia_at(container=tail_container, index=tail_index, items=items)
        return
    owner_position = _implicit_owner_position(chain=chain)
    if owner_position is not None:
        _insert_before(chain=chain[:-1], index=owner_position, items=items)
        return
    _insert_trivia_at(container=slot.container, index=index, items=items)


def _lift_out(*, toml_doc: TOMLDocument, parent_table: dict[str, Any], table_path: list[str], key: str) -> tuple[Item, list[Item]]:
    """Remove ``key`` from its parent, keeping the document's comments on the items they introduce.

    Returns the removed item and the trivia that introduced it. The removed item's own trailing run
    — the introduction of whatever came next — is put back where the item was, so the next item
    keeps its comment; the returned introduction is what a caller re-homes with the item, or drops
    with it. On a parent that carries no trivia, this is a plain deletion.
    """
    moved_value = cast("Item", parent_table[key])
    if not _carries_trivia(parent_table=parent_table):
        del parent_table[key]
        return moved_value, []
    chain = _slot_chain(toml_doc=toml_doc, path=[*table_path, key])
    introduction = _detach_run(run=_introduction_of_slot(chain=chain))
    last_container = _last_container(item=moved_value)
    trailing = _detach_run(run=_introduction(run=_trailing_run(container=last_container))) if last_container is not None else []
    # Detaching the introduction may have shifted the key's own positions in the same container.
    chain = _slot_chain(toml_doc=toml_doc, path=[*table_path, key])
    resting = chain[-1].last
    owner_position = _owner_position(chain=chain)
    opened_the_file = _opens_the_document(chain=chain)
    del parent_table[key]  # ``Container.remove`` leaves a ``Null`` in each slot, so positions hold.
    if owner_position is not None and _owner_position(chain=chain) is None:
        # The key was the last one of a chunk of an out-of-order table, and tomlkit dropped the
        # emptied chunk from the parent: what came after the key now comes right after that slot.
        _insert_before(chain=chain[:-1], index=owner_position + 1, items=trailing)
    else:
        _insert_before(chain=chain, index=resting + 1, items=trailing)
    if opened_the_file:
        _drop_leading_blank_line(toml_doc=toml_doc)
    return moved_value, introduction


def _opens_the_document(*, chain: list[_Slot]) -> bool:
    """Whether the key at the end of ``chain`` is the first thing in the file, in document order.

    It is when it comes first in its container and every parent on the way is itself first in
    its own, rendering no header — ``[runtime.storage]`` at the top of a file that never writes
    ``[runtime]``, or a dotted assignment opening the file.
    """
    for depth, link in enumerate(chain):
        if not _is_first_entry(container=link.container, index=link.first):
            return False
        if depth > 0 and _implicit_owner_position(chain=chain[: depth + 1]) is None:
            return False
    return True


def _drop_leading_blank_line(*, toml_doc: TOMLDocument) -> None:
    """A file does not open on a blank line: the one that separated the removed first entry from the next goes."""
    _drop_leading_blank_line_in(container=toml_doc)


def _drop_leading_blank_line_in(*, container: Container) -> bool:
    """Walk ``container`` in document order to its first rendered line, dropping it when it is blank.

    A table that renders no header — an implicit parent emptied by the removal, or one whose first
    entry is next — is walked through, since what opens the file is inside it. Returns whether the
    walk met anything that renders; ``False`` means the container renders nothing at all.
    """
    for position, (body_key, item) in enumerate(container.body):
        if isinstance(item, Null):
            continue
        if isinstance(item, Whitespace):
            _detach_run(run=_TriviaRun(container=container, positions=[position]))
            return True
        if isinstance(item, Table) and not _renders_header(table=item, key=body_key):
            if _drop_leading_blank_line_in(container=item.value):
                return True
            continue
        return True
    return False


def _settle_inserted(*, toml_doc: TOMLDocument, table_path: list[str], key: str, introduction: Sequence[Item]) -> None:
    """Give a just-inserted ``key`` its introduction, and the trivia around it back to what it introduces.

    Every insertion goes through here — a moved item, a key ``set_key`` adds, a table ``ensure_table``
    creates — with an empty introduction when there is nothing to carry. tomlkit appends a table
    after everything, including the trailing run that introduced whatever came after the container
    in the file — so that run is moved past the new item, to become the new item's own trailing run.
    A key it inserts *before the first table* of a container can land in the middle of a run —
    between a file's preamble and the blank line under it — so the run on both sides is read as
    one: what introduces the next item goes below the key, what does not (the preamble) goes back
    above it. The introduction is then inserted right above the item. A carried introduction brings
    the blank line the source had with it, so the newline tomlkit puts before an appended table's
    header is dropped in its favour.
    """
    chain = _slot_chain(toml_doc=toml_doc, path=[*table_path, key])
    if len(chain) < len(table_path) + 1:
        return  # beneath an inline table: nothing to settle
    slot = chain[-1]
    inserted = slot.container.body[slot.first][1]
    before = _run_before(container=slot.container, index=slot.first)
    after = _run_after(container=slot.container, index=slot.first)
    at_document_start = _at_document_start(run=before)
    if after.positions and before.container is slot.container:
        combined = _TriviaRun(container=slot.container, positions=[*before.positions, *after.positions])
        travelling = _introduction(run=combined, at_document_start=at_document_start).positions
        moving_down = _TriviaRun(container=slot.container, positions=[pos for pos in before.positions if pos in travelling])
        moving_up = _TriviaRun(container=slot.container, positions=[pos for pos in after.positions if pos not in travelling])
    else:
        moving_down = _introduction(run=before, at_document_start=at_document_start)
        moving_up = _TriviaRun(container=slot.container, positions=[])
    # Above-the-item positions come first in the body, so detaching the ones below first leaves them valid.
    up_items = _detach_run(run=moving_up)
    down_items = _detach_run(run=moving_down)
    chain = _slot_chain(toml_doc=toml_doc, path=[*table_path, key])
    slot = chain[-1]
    if up_items:
        _insert_trivia_at(container=slot.container, index=slot.first, items=up_items)
        chain = _slot_chain(toml_doc=toml_doc, path=[*table_path, key])
        slot = chain[-1]
    if down_items:
        last_container = _last_container(item=inserted)
        if last_container is None:
            # tomlkit gives the table that now follows an inserted key a newline of indent; that blank
            # line belongs above the run going back under the key, not between the run and the header.
            following = _first_entry_after(container=slot.container, index=slot.last)
            if isinstance(following, Table) and following.trivia.indent:
                if not isinstance(down_items[0], Whitespace):
                    down_items = [Whitespace(following.trivia.indent), *down_items]
                following.trivia.indent = ""
            _insert_trivia_at(container=slot.container, index=slot.last + 1, items=down_items)
        else:
            tail_container, tail_index = _tail_slot(container=last_container)
            _insert_trivia_at(container=tail_container, index=tail_index, items=down_items)
    if introduction:
        # tomlkit sets a table's indent to a newline when it appends it under content that does not
        # already end on a blank line. That blank line belongs *above* the carried introduction, not
        # between the introduction and the header, so it moves ahead of it unless the introduction
        # brought its own.
        lead: list[Item] = []
        if isinstance(inserted, Table) and inserted.trivia.indent and not isinstance(introduction[0], Whitespace):
            lead = [Whitespace(inserted.trivia.indent)]
        _insert_before(chain=chain, index=slot.first, items=[*lead, *introduction])
        if isinstance(inserted, Table):
            inserted.trivia.indent = ""


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
            was_absent = fix_op.key not in target_table
            target_table[fix_op.key] = _as_tomlkit_value(fix_op.value)
            if was_absent:
                # A new key lands before the table's trailing run — the next section's banner — not after it.
                _settle_inserted(toml_doc=toml_doc, table_path=table_path, key=fix_op.key, introduction=[])
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
            _settle_inserted(toml_doc=toml_doc, table_path=table_path[:-1], key=table_key, introduction=[])
            return _OpResult(FixOpOutcome.APPLIED)
        case DeleteKeyOp():
            target_table = _resolve_table(toml_doc=toml_doc, table_path=table_path)
            if target_table is None:
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            if fix_op.key not in target_table:
                return _OpResult(FixOpOutcome.SKIPPED, f"key '{fix_op.key}' not found in table '{table_path_str}'")
            # The comment above the key goes with it; the one above the next key stays there.
            _lift_out(toml_doc=toml_doc, parent_table=target_table, table_path=table_path, key=fix_op.key)
            return _OpResult(FixOpOutcome.APPLIED)
        case DeleteTableOp():
            parent_table = _resolve_table(toml_doc=toml_doc, table_path=table_path[:-1])
            table_key = table_path[-1]
            # The final segment must itself be a table — a scalar there is a drifted target
            # (same guarded-skip contract _resolve_table enforces for every other segment).
            if parent_table is None or not isinstance(parent_table.get(table_key), dict):
                return _OpResult(FixOpOutcome.SKIPPED, f"table '{table_path_str}' not found in document")
            # The banner introducing the table goes with it; the next section's banner stays put.
            _lift_out(toml_doc=toml_doc, parent_table=parent_table, table_path=table_path[:-1], key=table_key)
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
    # Only the string values are ones a mapping could have named, so they are what the report
    # counts against: a table also holding sub-tables or numbers would otherwise read as though the
    # operation had left values behind that it was never able to address.
    reachable = 0
    for key in list(target_table):
        if not isinstance(target_table[key], str):
            continue
        reachable += 1
        if _remap_one_value(target_table=target_table, key=key, mapping=mapping, table_path_str=table_path_str).outcome.did_apply:
            remapped += 1
    if not remapped:
        return _OpResult(FixOpOutcome.SKIPPED, f"no value in '{table_path_str}' is one this operation's mapping names")
    return _OpResult(FixOpOutcome.APPLIED, f"remapped {remapped} of {reachable} values in '{table_path_str}'")


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

    moved_value, introduction = _lift_out(toml_doc=toml_doc, parent_table=source_table, table_path=table_path, key=fix_op.key)
    destination = _create_block_table_path(toml_doc=toml_doc, table_path=fix_op.new_table_path)
    destination.leaf[fix_op.new_key] = moved_value
    # The introduction goes above whatever this operation put into a pre-existing container: the
    # moved item itself, or the outermost parent created for it — that is the header a reader sees.
    head = destination.head or _InsertionHead(table_path=fix_op.new_table_path, key=fix_op.new_key)
    _settle_inserted(toml_doc=toml_doc, table_path=head.table_path, key=head.key, introduction=introduction)
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


class _InsertionHead(NamedTuple):
    """A key just added to a pre-existing container — the outermost thing an insertion put in the file."""

    table_path: list[str]
    key: str


class _DestinationPath(NamedTuple):
    leaf: dict[str, Any]
    head: _InsertionHead | None
    """The first segment that had to be created, under the deepest node that already existed; ``None`` when every segment existed."""


def _create_block_table_path(*, toml_doc: TOMLDocument, table_path: list[str]) -> _DestinationPath:
    """Walk ``table_path``, creating missing segments as block tables, and return the leaf node.

    Block tables rather than inline ones, because this creates a *section* of a configuration
    file — a destination that will hold moved keys and be read by a human. Callers must have
    ruled out a non-table segment first; this function would silently overwrite one.
    """
    node = cast("dict[str, Any]", toml_doc)
    head: _InsertionHead | None = None
    for depth, segment in enumerate(table_path):
        if not isinstance(node.get(segment), dict):
            node[segment] = tomlkit.table()
            if head is None:
                head = _InsertionHead(table_path=table_path[:depth], key=segment)
        node = cast("dict[str, Any]", node[segment])
    return _DestinationPath(leaf=node, head=head)
