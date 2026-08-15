"""Value-domain narrowing — the schema change that keeps every path and still breaks every file.

A change can leave the path set untouched, leave every enumerated spelling in place, and still
make a user's valid file stop validating: `int` becomes `str`, a free string becomes an enum, a
bound moves from `ge=1` to `ge=5`. Read as a fingerprint diff those are additive-looking — nothing
was removed — so without this module the gate would ask for a golden regeneration, demand no
version bump and no entry, and the next boot would reject a file with a green gate behind it.

No operation in the vocabulary can repair an out-of-domain value, which is why the remedies this
names are the only two there are: an `unsafe` entry, which is reported to the user and never
applied, or a `remap_value` where the old spellings can be enumerated and the new schema's member
set makes the remap legal. That is a narrower set of remedies than a removal has, and it is the
honest one.

**What this cannot see.** Domain narrowing expressed in a *validator* — a non-empty check, a
cross-field invariant, a completeness rule over user-supplied keys — is invisible to any
projection of the annotations, so it stays the author's responsibility and the gate does not claim
it. See `docs/migration-ledger.md` → "The fingerprint" for the live instances.

A lost enumerated spelling is a narrowing too, but it is not `describe_narrowing`'s to report: the
coverage gate compares member sets by origin, following the entry's own renames, which nothing here
could do. What this module owns of it is the other direction — `lost_enumerated_spellings` decides
which of the old spellings really stopped being accepted, so that an enum relaxed into a free
string is read as the widening it is instead of as the loss of every member it had.
"""

from pipelex.migration.fingerprint import ENUM_TYPE, LITERAL_TYPE, STRING_TYPE, ConstraintKind, PathFingerprint

_UNION_JOIN = " | "

_LOWER_VALUE_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.GT, True), (ConstraintKind.GE, False))
_UPPER_VALUE_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.LT, True), (ConstraintKind.LE, False))
_LOWER_LENGTH_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.MIN_LENGTH, False),)
_UPPER_LENGTH_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.MAX_LENGTH, False),)


def describe_narrowing(*, before: PathFingerprint, after: PathFingerprint) -> list[str]:
    """Why the values this path accepts are fewer than they were — empty when they are not.

    Every reason is phrased so that it can be read on its own in a gate's output, because that is
    where it lands: the author sees the path and needs to know which half of the record moved.
    """
    reasons: list[str] = []
    if before.value_type != after.value_type and not _is_type_widening(before=before.value_type, after=after.value_type):
        reasons.append(f"its type went from '{before.value_type}' to '{after.value_type}'")
    reasons.extend(_describe_tightenings(before=before.constraints or {}, after=after.constraints or {}))
    return reasons


def lost_enumerated_spellings(*, before: PathFingerprint, after: PathFingerprint) -> list[str]:
    """The enumerated spellings the new schema no longer accepts at this path.

    A raw set difference is wrong in one common case: an enumerated type relaxed into a free string
    records no members afterwards, so every spelling it had reads as lost, while in truth every one
    of them still validates. That change is a widening and must ask for nothing — a bump demanded
    there is a gate crying wolf on a change no user's file notices.
    """
    if not before.enum_members:
        return []
    if not after.enum_members and _is_type_widening(before=before.value_type, after=after.value_type):
        return []
    return sorted(set(before.enum_members) - set(after.enum_members or []))


def _is_type_widening(*, before: str, after: str) -> bool:
    """Whether every value the old type accepted the new one still accepts.

    Two shapes qualify, and nothing else does. A union that keeps its members and gains more is a
    widening, member by member — a comparison of the whole rendered string would call `int` to
    `int | str` a change and demand a bump for it. And an enumerated type becoming `str` is a
    widening, because the enumerated spellings are strings and `str` accepts them all; the reverse
    is the narrowing this exists to catch.
    """
    after_members = _union_members(rendered=after)
    return all(_is_member_absorbed(member=member, after_members=after_members) for member in _union_members(rendered=before))


def _is_member_absorbed(*, member: str, after_members: set[str]) -> bool:
    if member in after_members:
        return True
    return member in {ENUM_TYPE, LITERAL_TYPE} and STRING_TYPE in after_members


def _union_members(*, rendered: str) -> set[str]:
    """The top-level members of a rendered type.

    Splitting has to respect brackets: `list[int | str]` is one member, not two, and treating it
    as two would let a genuine narrowing inside a container read as a widening.
    """
    members: set[str] = set()
    depth = 0
    current = ""
    for character in rendered:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        current += character
        if depth == 0 and current.endswith(_UNION_JOIN):
            members.add(current[: -len(_UNION_JOIN)])
            current = ""
    members.add(current)
    return members


def _describe_tightenings(*, before: dict[ConstraintKind, int | float], after: dict[ConstraintKind, int | float]) -> list[str]:
    """Every bound family whose new form admits fewer values than its old one.

    A bound that appears where there was none is a tightening; one that disappears is a widening
    and says nothing. The `gt`/`ge` pair is compared as a single lower bound rather than key by
    key, so swapping `gt=0` for `ge=0` reads as the widening it is instead of one key vanishing
    and another appearing.
    """
    reasons: list[str] = []
    for label, kinds, sign in (
        ("lower bound", _LOWER_VALUE_BOUND_KINDS, 1.0),
        ("upper bound", _UPPER_VALUE_BOUND_KINDS, -1.0),
        ("minimum length", _LOWER_LENGTH_BOUND_KINDS, 1.0),
        ("maximum length", _UPPER_LENGTH_BOUND_KINDS, -1.0),
    ):
        before_bound = _strictest_bound(constraints=before, kinds=kinds, sign=sign)
        after_bound = _strictest_bound(constraints=after, kinds=kinds, sign=sign)
        if after_bound is not None and (before_bound is None or after_bound > before_bound):
            reasons.append(
                f"its {label} tightened from {_render_bounds(constraints=before, kinds=kinds)} to {_render_bounds(constraints=after, kinds=kinds)}"
            )
    reasons.extend(_describe_multiple_of(before=before, after=after))
    return reasons


def _strictest_bound(
    *,
    constraints: dict[ConstraintKind, int | float],
    kinds: tuple[tuple[ConstraintKind, bool], ...],
    sign: float,
) -> tuple[float, bool] | None:
    """The binding constraint of one family, as a key that sorts by strictness — `None` for none.

    The sign flips an upper bound so that both directions sort the same way: a *higher* threshold
    binds a lower bound harder, a *lower* one binds an upper bound harder, and negating the second
    makes `max` mean "strictest" in both. Exclusivity breaks the tie, since `gt=0` admits one fewer
    value than `ge=0` at the same threshold.
    """
    keys = [(sign * constraints[kind], exclusive) for kind, exclusive in kinds if kind in constraints]
    return max(keys) if keys else None


def _render_bounds(*, constraints: dict[ConstraintKind, int | float], kinds: tuple[tuple[ConstraintKind, bool], ...]) -> str:
    present = [f"{kind}={constraints[kind]}" for kind, _ in kinds if kind in constraints]
    return ", ".join(present) if present else "unbounded"


def _describe_multiple_of(*, before: dict[ConstraintKind, int | float], after: dict[ConstraintKind, int | float]) -> list[str]:
    """`multiple_of` narrows unless the new step divides the old one.

    Multiples of four are a subset of multiples of two, so going from two to four is a tightening
    and going the other way is a widening. Steps that divide neither way — two to three — share
    only their common multiples, so most old values stop validating: a tightening, and reported as
    one rather than waved through for not being comparable.
    """
    before_step = before.get(ConstraintKind.MULTIPLE_OF)
    after_step = after.get(ConstraintKind.MULTIPLE_OF)
    if after_step is None or after_step == 0:
        return []
    if before_step is not None and before_step % after_step == 0:
        return []
    return [f"its step tightened from {'unbounded' if before_step is None else f'multiple_of={before_step}'} to multiple_of={after_step}"]
