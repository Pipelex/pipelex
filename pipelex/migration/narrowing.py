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

from fractions import Fraction

from pipelex.migration.fingerprint import (
    ENUM_TYPE,
    INTEGER_TYPE,
    LITERAL_TYPE,
    REAL_TYPE,
    STRING_TYPE,
    UNION_SEPARATOR,
    ConstraintKind,
    PathFingerprint,
)

_LOWER_VALUE_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.GT, True), (ConstraintKind.GE, False))
_UPPER_VALUE_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.LT, True), (ConstraintKind.LE, False))
_LOWER_LENGTH_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.MIN_LENGTH, False),)
_UPPER_LENGTH_BOUND_KINDS: tuple[tuple[ConstraintKind, bool], ...] = ((ConstraintKind.MAX_LENGTH, False),)
_STRING_TYPED_MEMBERS: frozenset[str] = frozenset({STRING_TYPE, ENUM_TYPE, LITERAL_TYPE})
_ENUMERATED_MEMBERS: frozenset[str] = frozenset({ENUM_TYPE, LITERAL_TYPE})
_ARGUMENT_SEPARATOR = ", "


def describe_narrowing(*, before: PathFingerprint, after: PathFingerprint, remapped: bool = False) -> list[str]:
    """Why the values this path accepts are fewer than they were — empty when they are not.

    Every reason is phrased so that it can be read on its own in a gate's output, because that is
    where it lands: the author sees the path and needs to know which half of the record moved.

    ``remapped`` is set when the entry carries a ``remap_value`` on this path. A remap rewrites
    string values, so it answers for a lost string-typed member — ``str``, ``enum``, ``literal`` —
    and for nothing else: a number the old type accepted and the new one does not (``int | literal``
    becoming ``literal``) is a value no mapping reaches, and so is a tightened bound. Both must
    still be reported, or they ride under the remap into a ``safe`` entry.
    """
    reasons: list[str] = []
    exempt = _STRING_TYPED_MEMBERS if remapped else frozenset[str]()
    if before.value_type != after.value_type and not _is_type_widening(before=before.value_type, after=after.value_type, exempt=exempt):
        reasons.append(f"its type went from '{before.value_type}' to '{after.value_type}'")
    reasons.extend(
        _describe_tightenings(
            before=before.constraints or {},
            after=after.constraints or {},
            over_integers=_is_integral(rendered=before.value_type) and _is_integral(rendered=after.value_type),
        )
    )
    return reasons


def lost_enumerated_spellings(*, before: PathFingerprint, after: PathFingerprint) -> list[str]:
    """The enumerated spellings the new schema no longer accepts at this path.

    A raw set difference is wrong in one common case: an enumerated type relaxed into a free string
    records no members afterwards, so every spelling it had reads as lost, while in truth every one
    of them still validates. That change is a widening and must ask for nothing — a bump demanded
    there is a gate crying wolf on a change no user's file notices.

    The exemption is exactly that case — every enumerated part of the old type absorbed by a new
    one that enumerates nothing — and not "the type did not narrow": `Literal['a']` to `Literal[1]`
    renders the same type on both sides and records no members after, and every file carrying `'a'`
    stops validating.

    It is read structurally, at whatever depth the spellings sit, because that is where the type
    half of this relation reads it: `list[enum]` to `list[str]` is the same benign loosening one
    container down, and answering it differently here would have the two halves contradict each
    other on one change. The depth cuts both ways — a `list[enum]` flattened to a bare `str` is no
    widening at all, and every spelling it had is lost with it.
    """
    if not before.enum_members:
        return []
    if not after.enum_members and _is_relaxed_into_free_strings(before=before.value_type, after=after.value_type):
        return []
    return sorted(set(before.enum_members) - set(after.enum_members or []))


def _is_relaxed_into_free_strings(*, before: str, after: str) -> bool:
    """Whether the new type still accepts every enumerated spelling the old one carried.

    Two conditions, and the first is what keeps this from reading as "the type did not narrow": the
    new type must enumerate nothing anywhere, so that a record with no members means "free" rather
    than "enumerated over values the fingerprint cannot spell". Then every old member that carried
    spellings must be absorbed — by `str`, or by the same member one container down.

    Members that carry no spellings are not asked to be absorbed. `enum | int` becoming `str` loses
    the numbers, and that is a narrowing of the *type*, reported by `describe_narrowing`; this half
    answers only for the spellings.
    """
    if _records_enumerated_members(rendered=after):
        return False
    after_members = _union_members(rendered=after)
    return all(
        _is_member_absorbed(member=member, after_members=after_members)
        for member in _union_members(rendered=before)
        if _records_enumerated_members(rendered=member)
    )


def _records_enumerated_members(*, rendered: str) -> bool:
    """Whether a rendered type spells out a closed set of values anywhere inside it.

    `enum` and `literal` do, at any depth: the members of a `list[enum]` are recorded on the list's
    own path, since a container argument gets no record of its own.
    """
    for member in _union_members(rendered=rendered):
        if member in _ENUMERATED_MEMBERS:
            return True
        _, arguments = _split_container(rendered=member)
        if any(_records_enumerated_members(rendered=argument) for argument in arguments):
            return True
    return False


def is_remappable(*, record: PathFingerprint) -> bool:
    """Whether a `remap_value` on this path can ever rewrite anything.

    The operation rewrites a *string* value, so it reaches a path whose own value is string-typed
    — `str`, `enum`, `literal`, or a union carrying one. A `list[enum]` is not: its value is a
    list, so the operation is a guarded skip on every run. Crediting such a remap in the
    accounting would leave a green gate over a file that stops validating, and offering it as a
    remedy would send the author to write an operation they will never see fire. The enumerated
    members beneath an *open mapping* are recorded on that mapping's `*` child, whose own value
    is the enumerated one, so they are remappable there — through `key = "*"`.
    """
    return bool(_union_members(rendered=record.value_type) & _STRING_TYPED_MEMBERS)


def _is_type_widening(*, before: str, after: str, exempt: frozenset[str]) -> bool:
    """Whether every value the old type accepted the new one still accepts.

    Two shapes qualify, and nothing else does. A union that keeps its members and gains more is a
    widening, member by member — a comparison of the whole rendered string would call `int` to
    `int | str` a change and demand a bump for it. And an enumerated type becoming `str` is a
    widening, because the enumerated spellings are strings and `str` accepts them all; the reverse
    is the narrowing this exists to catch. An ``exempt`` old member is one something else answers
    for, and is not asked to be absorbed.
    """
    after_members = _union_members(rendered=after)
    return all(_is_member_absorbed(member=member, after_members=after_members) for member in _union_members(rendered=before) - exempt)


def _is_member_absorbed(*, member: str, after_members: set[str]) -> bool:
    """Whether one old union member's values all survive somewhere in the new type.

    Four readings, and each closes a shape the plain set comparison called a narrowing while every
    file survived it:

    - the member is still there verbatim;
    - an enumerated member (`enum`, `literal`) absorbed by `str`, or by the *other* enumerated
      rendering — `enum` and `literal` are two spellings of one thing, a closed set of string
      values, and what moved between two member *sets* is reported by `lost_enumerated_spellings`
      rather than by this half;
    - `int` absorbed by `float`, which accepts every integer, in strict validation as well as lax;
    - a container whose head and arity are unchanged and each of whose arguments is itself
      absorbed — `list[int]` becoming `list[int | str]` widens the list.
    """
    if member in after_members:
        return True
    if member in _ENUMERATED_MEMBERS and (STRING_TYPE in after_members or after_members & _ENUMERATED_MEMBERS):
        return True
    if member == INTEGER_TYPE and REAL_TYPE in after_members:
        return True
    return any(_is_container_widening(before=member, after=candidate) for candidate in after_members)


def _is_container_widening(*, before: str, after: str) -> bool:
    """Whether two rendered container types have the same shape and every argument widened."""
    before_head, before_args = _split_container(rendered=before)
    after_head, after_args = _split_container(rendered=after)
    if before_head is None or before_head != after_head or len(before_args) != len(after_args):
        return False
    return all(
        _is_type_widening(before=before_arg, after=after_arg, exempt=frozenset[str]())
        for before_arg, after_arg in zip(before_args, after_args, strict=True)
    )


def _split_container(*, rendered: str) -> tuple[str | None, list[str]]:
    """A rendered `head[arg, arg]` split into its head and its top-level arguments.

    `(None, [])` for anything that is not a parameterized container, which is what makes the
    caller's comparison say "not the same shape" rather than "no arguments, so vacuously equal".
    """
    if not rendered.endswith("]") or "[" not in rendered:
        return None, []
    head, _, inside = rendered.partition("[")
    return head, _split_top_level(rendered=inside[:-1], separator=_ARGUMENT_SEPARATOR)


def _union_members(*, rendered: str) -> set[str]:
    """The top-level members of a rendered type.

    Splitting has to respect brackets: `list[int | str]` is one member, not two, and treating it
    as two would let a genuine narrowing inside a container read as a widening.
    """
    return set(_split_top_level(rendered=rendered, separator=UNION_SEPARATOR))


def _split_top_level(*, rendered: str, separator: str) -> list[str]:
    """Split a rendered type on a separator that appears outside every bracket pair, in order."""
    parts: list[str] = []
    depth = 0
    current = ""
    for character in rendered:
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        current += character
        if depth == 0 and current.endswith(separator):
            parts.append(current[: -len(separator)])
            current = ""
    parts.append(current)
    return parts


def _is_integral(*, rendered: str) -> bool:
    """Whether every numeric value this type accepts is a whole number.

    Only then are `gt=n` and `ge=n+1` the same bound. The string-typed members are set aside — a
    real shape is `int | literal`, where the literal spellings are not what a numeric bound is
    about — and what remains has to be exactly `int`.
    """
    numeric_members = _union_members(rendered=rendered) - _STRING_TYPED_MEMBERS
    return numeric_members == {INTEGER_TYPE}


def _describe_tightenings(*, before: dict[ConstraintKind, int | float], after: dict[ConstraintKind, int | float], over_integers: bool) -> list[str]:
    """Every bound family whose new form admits fewer values than its old one.

    A bound that appears where there was none is a tightening; one that disappears is a widening
    and says nothing. The `gt`/`ge` pair is compared as a single lower bound rather than key by
    key, so swapping `gt=0` for `ge=0` reads as the widening it is instead of one key vanishing
    and another appearing.

    ``over_integers`` says the path's numeric values are whole numbers, which makes `gt=n` and
    `ge=n+1` the same bound. Length bounds are counts and are integral whatever the value type is,
    so they are compared that way always.
    """
    reasons: list[str] = []
    for label, kinds, sign, integral in (
        ("lower bound", _LOWER_VALUE_BOUND_KINDS, 1.0, over_integers),
        ("upper bound", _UPPER_VALUE_BOUND_KINDS, -1.0, over_integers),
        ("minimum length", _LOWER_LENGTH_BOUND_KINDS, 1.0, True),
        ("maximum length", _UPPER_LENGTH_BOUND_KINDS, -1.0, True),
    ):
        before_bound = _strictest_bound(constraints=before, kinds=kinds, sign=sign, integral=integral)
        after_bound = _strictest_bound(constraints=after, kinds=kinds, sign=sign, integral=integral)
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
    integral: bool,
) -> tuple[float, bool] | None:
    """The binding constraint of one family, as a key that sorts by strictness — `None` for none.

    The sign flips an upper bound so that both directions sort the same way: a *higher* threshold
    binds a lower bound harder, a *lower* one binds an upper bound harder, and negating the second
    makes `max` mean "strictest" in both. Exclusivity breaks the tie, since `gt=0` admits one fewer
    value than `ge=0` at the same threshold.

    Over the integers a bound is met at the first whole number past its threshold, so every
    spelling of one bound folds onto that number before anything is compared: `gt=t` binds at
    `floor(t) + 1` and `ge=t` at `ceil(t)`. For a whole threshold — which is what `gt=0` *is*
    `ge=1` says, and the only kind pydantic will build on an integer field — both are identities
    beyond turning the exclusive form inclusive. For a fractional one they are what stops `gt=0.5`
    and `gt=0.9`, which admit exactly the same integers, from reading as a tightening.
    """
    keys: list[tuple[float, bool]] = []
    for kind, exclusive in kinds:
        if kind not in constraints:
            continue
        threshold = sign * constraints[kind]
        if integral:
            keys.append((_first_integer_meeting(threshold=threshold, exclusive=exclusive), False))
            continue
        keys.append((threshold, exclusive))
    return max(keys) if keys else None


def _first_integer_meeting(*, threshold: float, exclusive: bool) -> float:
    """The smallest whole number that satisfies this bound, in the signed comparison domain.

    Read exactly rather than in binary floating point — `Fraction` for the same reason
    `_is_multiple` uses it, so a threshold a user wrote as a decimal is not floored one short of
    itself by a representation error.
    """
    exact = Fraction(str(threshold))
    floored = exact.numerator // exact.denominator
    if exclusive:
        return float(floored + 1)
    return float(floored if exact.denominator == 1 else floored + 1)


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
    # Divisibility is decided over exact rationals: `0.3 % 0.1` is not zero in binary floating
    # point, and a relaxed step must not read as a tightened one.
    if before_step is not None and Fraction(str(before_step)) % Fraction(str(after_step)) == 0:
        return []
    return [f"its step tightened from {'unbounded' if before_step is None else f'multiple_of={before_step}'} to multiple_of={after_step}"]
