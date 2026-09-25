"""Unit tests for the ambient caller and the stamp an escaping exception carries.

The scope is what lets a capture with no run in hand — the validation sweep's
event, an exception raised while a pipe ran — still name the caller it was made
for. These tests pin its three promises: it is current inside the block and
gone after it, `None` inherits rather than clears, and an exception leaving the
block remembers the caller it escaped from, innermost scope first.
"""

import asyncio

import pytest
from pydantic import ValidationError
from typing_extensions import override

from pipelex.system.caller_identity import (
    CallerIdentity,
    find_stamped_caller_identity,
    get_current_caller_identity,
    scoped_caller_identity,
    stamp_caller_identity,
)
from pipelex.system.job_metadata import RunMetadata

_ALICE = CallerIdentity(user_id="user-alice", extras={"organization": "org_acme"})
_BOB = CallerIdentity(user_id="user-bob")


class _SlottedError(Exception):
    """An error type that refuses new attributes, so it cannot carry a stamp."""

    __slots__ = ()

    @override
    def __setattr__(self, name: str, value: object) -> None:
        msg = f"'{type(self).__name__}' refuses attribute '{name}'"
        raise AttributeError(msg)


class TestCallerIdentity:
    def test_it_is_built_from_a_runs_metadata(self) -> None:
        run_metadata = RunMetadata(
            user_id="user-42",
            pipeline_run_id="run-1",
            storage_scope="tenant/run-1",
            extras={"organization": "org_acme"},
        )

        caller_identity = CallerIdentity.make_from_run_metadata(run_metadata=run_metadata)

        assert caller_identity == CallerIdentity(user_id="user-42", extras={"organization": "org_acme"})

    def test_a_host_with_no_groups_states_an_empty_mapping(self) -> None:
        assert CallerIdentity.make_from_host(user_id="user-42", extras=None).extras == {}

    def test_its_groups_are_validated_like_a_runs(self) -> None:
        """The groups reach a telemetry backend, so a malformed key is refused at construction."""
        with pytest.raises(ValidationError, match="extras"):
            CallerIdentity(user_id="user-42", extras={"organization": "has a space"})

    def test_there_is_no_caller_outside_every_scope(self) -> None:
        assert get_current_caller_identity() is None

    def test_the_caller_is_current_inside_the_block_and_gone_after_it(self) -> None:
        with scoped_caller_identity(caller_identity=_ALICE) as current:
            assert current == _ALICE
            assert get_current_caller_identity() == _ALICE
        assert get_current_caller_identity() is None

    def test_none_inherits_the_caller_already_in_scope(self) -> None:
        """A caller-less entry point nested in a caller's work still works for that caller."""
        with scoped_caller_identity(caller_identity=_ALICE):
            with scoped_caller_identity(caller_identity=None) as current:
                assert current == _ALICE
            assert get_current_caller_identity() == _ALICE

    def test_an_inner_caller_replaces_the_outer_one_until_it_closes(self) -> None:
        with scoped_caller_identity(caller_identity=_ALICE):
            with scoped_caller_identity(caller_identity=_BOB):
                assert get_current_caller_identity() == _BOB
            assert get_current_caller_identity() == _ALICE

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_see_each_others_caller(self) -> None:
        """A `ContextVar`, so two requests served on one event loop stay apart."""
        seen: dict[str, CallerIdentity | None] = {}

        async def serve(*, caller_identity: CallerIdentity, name: str) -> None:
            with scoped_caller_identity(caller_identity=caller_identity):
                await asyncio.sleep(0)
                seen[name] = get_current_caller_identity()

        await asyncio.gather(serve(caller_identity=_ALICE, name="alice"), serve(caller_identity=_BOB, name="bob"))

        assert seen == {"alice": _ALICE, "bob": _BOB}

    def test_an_exception_leaving_the_block_is_stamped_and_still_propagates(self) -> None:
        msg = "boom"
        with pytest.raises(ValueError, match="boom") as exc_info, scoped_caller_identity(caller_identity=_ALICE):
            raise ValueError(msg)

        assert find_stamped_caller_identity(exception=exc_info.value) == _ALICE
        assert get_current_caller_identity() is None

    def test_the_innermost_scope_wins_the_stamp(self) -> None:
        """The scope closest to the failure knows the work it came from; an outer one never overwrites it."""
        msg = "boom"
        with (
            pytest.raises(ValueError, match="boom") as exc_info,
            scoped_caller_identity(caller_identity=_ALICE),
            scoped_caller_identity(caller_identity=_BOB),
        ):
            raise ValueError(msg)

        assert find_stamped_caller_identity(exception=exc_info.value) == _BOB

    def test_a_scope_that_opened_nothing_stamps_nothing(self) -> None:
        msg = "boom"
        with pytest.raises(ValueError, match="boom") as exc_info, scoped_caller_identity(caller_identity=None):
            raise ValueError(msg)

        assert find_stamped_caller_identity(exception=exc_info.value) is None

    def test_an_exception_that_refuses_attributes_still_propagates(self) -> None:
        """Telemetry must never change how an error travels."""
        with pytest.raises(_SlottedError), scoped_caller_identity(caller_identity=_ALICE):
            raise _SlottedError

        assert get_current_caller_identity() is None

    def test_it_reads_the_stamp_through_an_explicit_cause(self) -> None:
        """A host re-raises its own error `from` the run's, and that outer error is what reaches the hook."""
        inner = ValueError("inner")
        stamp_caller_identity(exception=inner, caller_identity=_ALICE)
        outer = RuntimeError("outer")
        outer.__cause__ = inner

        assert find_stamped_caller_identity(exception=outer) == _ALICE

    def test_it_reads_the_stamp_through_an_implicit_context(self) -> None:
        inner = ValueError("inner")
        stamp_caller_identity(exception=inner, caller_identity=_ALICE)
        outer = RuntimeError("outer")
        outer.__context__ = inner

        assert find_stamped_caller_identity(exception=outer) == _ALICE

    def test_it_reads_the_stamp_inside_an_exception_group(self) -> None:
        member = ValueError("member")
        stamp_caller_identity(exception=member, caller_identity=_ALICE)

        assert find_stamped_caller_identity(exception=ExceptionGroup("group", [member])) == _ALICE

    def test_a_cyclic_chain_terminates(self) -> None:
        first = ValueError("first")
        second = ValueError("second")
        first.__context__ = second
        second.__context__ = first

        assert find_stamped_caller_identity(exception=first) is None

    def test_an_existing_stamp_is_never_replaced(self) -> None:
        error = ValueError("boom")
        stamp_caller_identity(exception=error, caller_identity=_ALICE)
        stamp_caller_identity(exception=error, caller_identity=_BOB)

        assert find_stamped_caller_identity(exception=error) == _ALICE
