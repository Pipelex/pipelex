"""`CallerIdentity` — who asked for the work in progress, and what they belong to.

**The run is not the only place a caller is known.** `RunMetadata` carries the
caller of a run, and every capture a run emits hands it over explicitly. But a
host also serves work that is not a run — a validation sweep, whose dry runs
exist only to check a bundle — and a crash reaches the interpreter's exception
hooks with nothing but `(type, value, traceback)`. Before this module both
reported under the stream's configured fallback, so on a hosted plane every
validation and every crash landed on one constant id per deployment while the
caller who caused it was known all along.

**Two facts, one object.** A caller is the `user_id` the host states and the
opaque `analytics_groups` it attaches — the same two facts `RunMetadata` holds,
without the per-run fields (`pipeline_run_id`, `storage_scope`) that work which
is not a run does not have. Whether a given `user_id` may be attributed to a
person is not decided here: telemetry decides it, once, in
:mod:`pipelex.system.telemetry.telemetry_identity`, so a placeholder such as
`"local"` travels as it is and still resolves to the stream's fallback.

**The ambient caller.** :func:`scoped_caller_identity` makes a caller the
current one for the duration of a block, through a `ContextVar`, so a capture
that has no run in hand — the validation sweep's event, an exception captured
while a pipe runs — reads it instead of falling back. A pipe run opens that
scope from its own `RunMetadata`, so every pipe, at every depth, is covered.

**An exception remembers the caller it escaped from.** By the time an unhandled
exception reaches `sys.excepthook` the stack has unwound and every scope has
closed, so the `ContextVar` alone would always be empty there. The scope
therefore stamps an exception that leaves it with the caller it was serving —
the innermost scope wins, an outer one never overwrites it — and the capture
reads the stamp back, walking the cause and context chain, because a host
usually re-raises its own error `from` the one that escaped the run.
"""

from contextvars import ContextVar, Token
from types import TracebackType
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.system.analytics_groups import validate_analytics_groups

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata

# The attribute an exception carries the caller it escaped from under. Namespaced,
# so it can never collide with an attribute an exception class defines itself.
_CALLER_IDENTITY_STAMP = "__pipelex_caller_identity__"


class CallerIdentity(BaseModel):
    """The caller a piece of work is done for: a user and the groups they belong to.

    Frozen, and the groups are validated at construction exactly as
    `RunMetadata.analytics_groups` is, because they reach a telemetry backend.
    """

    model_config = ConfigDict(frozen=True)

    # The host's own id for the caller, as `RunMetadata.user_id` states it.
    # Placeholders are legal and travel unchanged: whether this id may name a
    # person is decided by telemetry, not here.
    user_id: str

    # The opaque groups the caller belongs to — see `pipelex.system.analytics_groups`.
    analytics_groups: dict[str, str] = Field(default_factory=dict)

    @field_validator("analytics_groups")
    @classmethod
    def _validate_analytics_groups(cls, value: dict[str, str]) -> dict[str, str]:
        return validate_analytics_groups(value=value)

    @classmethod
    def make_from_run_metadata(cls, *, run_metadata: "RunMetadata") -> "CallerIdentity":
        """The caller of a run, read from the run half of its job metadata."""
        return cls(user_id=run_metadata.user_id, analytics_groups=dict(run_metadata.analytics_groups))

    @classmethod
    def make_from_host(cls, *, user_id: str, analytics_groups: dict[str, str] | None) -> "CallerIdentity":
        """The caller a host states, with no groups meaning an empty mapping."""
        return cls(user_id=user_id, analytics_groups=dict(analytics_groups or {}))


_current_caller_identity: ContextVar[CallerIdentity | None] = ContextVar("current_caller_identity", default=None)


def get_current_caller_identity() -> CallerIdentity | None:
    """The caller of the work in progress in this context, or None when no scope is open."""
    return _current_caller_identity.get()


class CallerIdentityScope:
    """The context manager behind :func:`scoped_caller_identity`.

    A class rather than a `@contextmanager` generator because it must see the
    exception leaving the block — to stamp it — without catching it: `__exit__`
    receives it and returns None, so it propagates untouched.
    """

    def __init__(self, caller_identity: CallerIdentity | None) -> None:
        self._caller_identity = caller_identity
        self._token: Token[CallerIdentity | None] | None = None

    def __enter__(self) -> CallerIdentity | None:
        if self._caller_identity is not None:
            self._token = _current_caller_identity.set(self._caller_identity)
        return get_current_caller_identity()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if self._token is None:
            return
        if exc_value is not None and self._caller_identity is not None:
            stamp_caller_identity(exception=exc_value, caller_identity=self._caller_identity)
        _current_caller_identity.reset(self._token)
        self._token = None


def scoped_caller_identity(*, caller_identity: CallerIdentity | None) -> CallerIdentityScope:
    """Make `caller_identity` the current caller for the duration of a `with` block.

    `None` opens no scope at all: the block inherits whatever caller is already
    current, which is what a caller-less entry point nested in a caller's work
    should see.
    """
    return CallerIdentityScope(caller_identity)


def stamp_caller_identity(*, exception: BaseException, caller_identity: CallerIdentity) -> None:
    """Record on `exception` the caller it escaped from, unless a closer scope already did.

    The innermost scope is the one that knows the work the error came from, so
    an existing stamp is never replaced. An exception type that refuses new
    attributes simply goes unstamped: telemetry must never change how an error
    propagates.
    """
    if hasattr(exception, _CALLER_IDENTITY_STAMP):
        return
    try:
        setattr(exception, _CALLER_IDENTITY_STAMP, caller_identity)
    except (AttributeError, TypeError):
        # An exception type with `__slots__` or a read-only `__setattr__` cannot carry the stamp.
        return


def find_stamped_caller_identity(*, exception: BaseException) -> CallerIdentity | None:
    """The caller `exception` escaped from, read from it or from any error it links to.

    Walks `__cause__`, `__context__` and the members of an exception group, as
    PostHog's own capture does, because a host that catches a run's error
    usually raises its own `from` it, and that outer error is what reaches the
    interpreter hook. A loop and not a recursion, so a long chain cannot fail the
    lookup, and a seen-set so a cyclic chain cannot loop forever.
    """
    pending: list[BaseException | None] = [exception]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in visited:
            continue
        visited.add(id(current))
        stamped = getattr(current, _CALLER_IDENTITY_STAMP, None)
        if isinstance(stamped, CallerIdentity):
            return stamped
        pending.append(current.__context__)
        pending.append(current.__cause__)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return None
