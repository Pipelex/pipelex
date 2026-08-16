"""Generating documents that are valid at a surface's current schema.

Replay neutrality is claimed over *every* document the current models accept, and a witness
document cannot stand in for that domain — the packaged defaults and the kit template each carry
exactly one value per key. This module is the sampler that stands in for it instead;
`test_replay_properties.py` is what asks the sampler questions.

**The fingerprint proposes a mutation; the model decides whether it lands.** That division is the
whole design, and it is forced: *schema membership is decided by validators the fingerprint
cannot see*. Three findings, each one a mutation this generator tried and had to give up on:

- `custom_posthog.mode = "identified"` is a perfectly legal member of a closed set, and it is
  rejected unless the document also carries a `user_id` — a requirement no type records.
- Several nodes typed `dict[str, X]` on the main configuration surface — every
  `effort_to_level_map`, `quality_to_steps_maps` — reject a key outside a fixed set, so their key
  space is not the user's at all despite the annotation saying so. `open_node` is a claim about
  the annotation and a validator can contradict it.
- `cogt.img_gen_config.img_gen_param_defaults.safety_tolerance` carries `Field(le=6)`, which the
  fingerprint does not record today — recording numeric constraints is exactly what the
  value-domain-narrowing rule adds.

The two shapes that answer are both wrong. A sampler that consults only the fingerprint is
confined to *dropping keys* — sound for every surface without looking at anything, because a
user's file is read merged beneath the defaults layer, so a dropped key is restored by the merge —
and a drop-only sampler can never reach a different *value*, which is the whole reason a property
beats the convergence witness. A sampler that mutates whatever the annotation allows and does not
check is red only when it happens to pick the wrong path, and the remedy everyone learns for that
is to grow an exclusion list, which is how a gate dies.

So this one proposes from the fingerprint and checks each proposal against the model, **one
mutation at a time**: a proposal the model rejects is simply not made, and the document keeps the
value it had. Checking per mutation rather than filtering whole documents is what keeps the
sampler from quietly shrinking to nothing — every draw yields a document, and `mutations` reports
what actually survived, so a test can tell a rich sampler from a degenerate one.

Three mutations are proposed:

- **Dropping a path** — any path, including a whole table and a user-owned key beneath an open
  node. Sound for the defaults-layer reason above, and the mutation that matters most, because a
  sparse file is the shape most user files actually have.
- **Swapping an enumerated spelling** for another member of the set the fingerprint records. This
  is the one value shape an operation's precondition can mention: the remap legality rule confines
  a `safe` `remap_value` to an enum-typed path.
- **Flipping a boolean**, whose entire domain is the two values it can hold.

Numbers and free strings are not perturbed at all, and that costs the property nothing: no
operation in the vocabulary has a precondition that mentions one, so perturbing a number or a free
string cannot separate a neutral replay from a non-neutral one.

See `docs/migration-ledger.md` → "Replay neutrality" and "The fingerprint".
"""

from enum import StrEnum
from typing import Any, cast

import tomlkit
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.migration.documents import flatten_document
from pipelex.migration.fingerprint import ENUM_TYPE, PATH_SEPARATOR, PathFingerprint, SurfaceFingerprint, compute_fingerprint
from pipelex.migration.surfaces import Surface
from pipelex.suggested_fix import WILDCARD_SEGMENT
from pipelex.system.configuration.config_surface import strip_reserved_meta
from pipelex.system.exceptions import ConfigValidationError
from pipelex.tools.misc.json_utils import deep_update

BOOL_TYPE = "bool"

MAX_DROPPED_PATHS = 6
MAX_SWAPPED_ENUM_MEMBERS = 4
MAX_FLIPPED_BOOLS = 4
"""Bounds per document. Hypothesis shrinks a set toward the empty one, so the smallest
counterexample any failure reports is the reference document with one mutation on it."""


class DocumentMutation(StrEnum):
    """A kind of within-schema edit the generator made to a reference document."""

    DROPPED_PATH = "dropped_path"
    SWAPPED_ENUM_MEMBER = "swapped_enum_member"
    FLIPPED_BOOL = "flipped_bool"


class GeneratedDocument(BaseModel):
    """One sampled document, and what actually survived being made to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    mutations: list[DocumentMutation] = Field(default_factory=list[DocumentMutation])


def surface_fingerprint(*, surface: Surface) -> SurfaceFingerprint:
    """The surface's model tree projected against its own defaults, at its current shape."""
    return compute_fingerprint(
        surface_id=surface.surface_id,
        schema_version=1,
        config_model=surface.config_model,
        defaults_document=surface.read_defaults_document(),
    )


def merge_beneath_defaults(*, surface: Surface, document: dict[str, Any]) -> dict[str, Any]:
    """A file's content as the models will really see it: merged beneath the defaults layer.

    Validating a user's file on its own would report the defaults layer doing its job as a
    failure — an absent optional key is the normal shape of a configuration file, not an error.
    """
    merged: dict[str, Any] = surface.read_defaults_document()
    deep_update(merged, updates=document)
    strip_reserved_meta(config_dict=merged)
    return merged


def merge_text_beneath_defaults(*, surface: Surface, text: str) -> dict[str, Any]:
    """`merge_beneath_defaults` starting from a document's text rather than its mapping."""
    return merge_beneath_defaults(surface=surface, document=tomlkit.loads(text).unwrap())


def is_accepted_by_the_surface(*, surface: Surface, document: dict[str, Any]) -> bool:
    """Whether the models accept this document — the only authority on schema membership."""
    try:
        surface.config_model.model_validate(merge_beneath_defaults(surface=surface, document=document))
    except (ValidationError, ConfigValidationError):
        # Both spellings of the same answer: a `ConfigRoot` re-raises pydantic's rejection as its
        # own error, and the surfaces are a mix of the two.
        return False
    return True


def within_schema_documents(*, surface: Surface) -> st.SearchStrategy[GeneratedDocument]:
    """Documents a user could legitimately have, at the surface's current schema."""
    fingerprint = surface_fingerprint(surface=surface)
    flattened = flatten_document(document=surface.read_defaults_document())

    return _sampled_documents(
        surface=surface,
        fingerprint=fingerprint,
        droppable=sorted(flattened),
        swappable=sorted(path for path, value in flattened.items() if _is_swappable_enum(fingerprint=fingerprint, path=path, value=value)),
        flippable=sorted(path for path, value in flattened.items() if _is_flippable_bool(fingerprint=fingerprint, path=path, value=value)),
    )


@st.composite
def _sampled_documents(  # kw-only: ignore — Hypothesis passes `draw` positionally to a composite's body.
    draw: st.DrawFn,
    *,
    surface: Surface,
    fingerprint: SurfaceFingerprint,
    droppable: list[str],
    swappable: list[str],
    flippable: list[str],
) -> GeneratedDocument:
    dropped = draw(_path_subsets(paths=droppable, max_size=MAX_DROPPED_PATHS))
    swapped = draw(_path_subsets(paths=swappable, max_size=MAX_SWAPPED_ENUM_MEMBERS))
    flipped = draw(_path_subsets(paths=flippable, max_size=MAX_FLIPPED_BOOLS))

    document = surface.read_defaults_document()
    mutations: list[DocumentMutation] = []

    for path in sorted(swapped):
        alternatives = [member for member in _members_at(fingerprint=fingerprint, path=path) if member != _value_at(mapping=document, path=path)]
        if not alternatives:
            continue
        if _assign_if_accepted(surface=surface, document=document, path=path, value=draw(st.sampled_from(alternatives))):
            _record(mutations=mutations, mutation=DocumentMutation.SWAPPED_ENUM_MEMBER)

    for path in sorted(flipped):
        if _assign_if_accepted(surface=surface, document=document, path=path, value=not _value_at(mapping=document, path=path)):
            _record(mutations=mutations, mutation=DocumentMutation.FLIPPED_BOOL)

    # Dropping runs last and is never checked, because the defaults layer restores whatever it
    # removes: the document the models see is the same one they just accepted.
    for path in sorted(dropped):
        if _drop(mapping=document, path=path):
            _record(mutations=mutations, mutation=DocumentMutation.DROPPED_PATH)

    text: str = tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]
    return GeneratedDocument(text=text, mutations=mutations)


def _record(*, mutations: list[DocumentMutation], mutation: DocumentMutation) -> None:
    if mutation not in mutations:
        mutations.append(mutation)


def _path_subsets(*, paths: list[str], max_size: int) -> st.SearchStrategy[set[str]]:
    if not paths:
        return st.just(set[str]())
    return st.sets(st.sampled_from(paths), max_size=max_size)


def _is_swappable_enum(*, fingerprint: SurfaceFingerprint, path: str, value: Any) -> bool:
    entry = fingerprint_at(fingerprint=fingerprint, path=path)
    if entry is None or entry.value_type != ENUM_TYPE or not entry.enum_members:
        return False
    return isinstance(value, str) and len(entry.enum_members) > 1


def _is_flippable_bool(*, fingerprint: SurfaceFingerprint, path: str, value: Any) -> bool:
    entry = fingerprint_at(fingerprint=fingerprint, path=path)
    return entry is not None and entry.value_type == BOOL_TYPE and isinstance(value, bool)


def fingerprint_at(*, fingerprint: SurfaceFingerprint, path: str) -> PathFingerprint | None:
    """What the fingerprint says about a *document* path, `None` when it says nothing.

    A document path and a fingerprint path are not the same language: beneath an open node the
    document carries the user's own key where the fingerprint carries a `*`. Walking segment by
    segment, and substituting `*` the moment the parent is an open node, translates one into the
    other — including through nesting, where `dict[str, dict[str, int]]` addresses `a.*.*`.
    """
    translated: list[str] = []
    for segment in path.split(PATH_SEPARATOR):
        parent = fingerprint.paths.get(PATH_SEPARATOR.join(translated)) if translated else None
        translated.append(WILDCARD_SEGMENT if parent is not None and parent.open_node else segment)
        if PATH_SEPARATOR.join(translated) not in fingerprint.paths:
            return None
    return fingerprint.paths[PATH_SEPARATOR.join(translated)]


def _members_at(*, fingerprint: SurfaceFingerprint, path: str) -> list[str]:
    entry = fingerprint_at(fingerprint=fingerprint, path=path)
    return list(entry.enum_members) if entry is not None and entry.enum_members else []


def _assign_if_accepted(*, surface: Surface, document: dict[str, Any], path: str, value: Any) -> bool:
    """Write a value, keep it only if the models still accept the document, and say which."""
    located = _parent_of(mapping=document, path=path)
    if located is None:
        return False
    parent, key = located
    previous = parent[key]
    parent[key] = value
    if is_accepted_by_the_surface(surface=surface, document=document):
        return True
    parent[key] = previous
    return False


def _parent_of(*, mapping: dict[str, Any], path: str) -> tuple[dict[str, Any], str] | None:
    segments = path.split(PATH_SEPARATOR)
    node = mapping
    for segment in segments[:-1]:
        child = node.get(segment)
        if not isinstance(child, dict):
            return None
        node = cast("dict[str, Any]", child)
    return (node, segments[-1]) if segments[-1] in node else None


def _value_at(*, mapping: dict[str, Any], path: str) -> Any:
    located = _parent_of(mapping=mapping, path=path)
    return located[0][located[1]] if located is not None else None


def _drop(*, mapping: dict[str, Any], path: str) -> bool:
    """Remove a path and, when it names a table, everything beneath it.

    A path whose parent an earlier drop already removed is simply absent, which is why this
    reports rather than insists: the drawn set is a set of paths, not a set of independent edits.
    """
    located = _parent_of(mapping=mapping, path=path)
    if located is None:
        return False
    del located[0][located[1]]
    return True
