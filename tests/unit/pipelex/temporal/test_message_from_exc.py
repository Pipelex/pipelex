"""Unit tests for ``_message_from_exc`` — deepest-message extraction from a Temporal failure chain.

Covers the two robustness paths that have no other coverage: the ``id()``-based
cycle guard on a self-referential ``__cause__`` chain, and the ``repr(exc)``
fallback when every message in the chain is empty.
"""

from pipelex.temporal.tprl.temporal_error import _message_from_exc  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]


class TestMessageFromExc:
    def test_self_referential_cause_chain_terminates(self) -> None:
        """A cyclic ``__cause__`` chain must not loop forever — the ``id()`` guard stops the walk
        once a node is revisited, after surfacing the deepest message reached.
        """
        first = RuntimeError("first failure")
        second = RuntimeError("second failure")
        first.__cause__ = second
        second.__cause__ = first
        assert _message_from_exc(first) == "second failure"

    def test_repr_fallback_when_every_message_empty(self) -> None:
        """When every exception in the chain has an empty message, fall back to ``repr(exc)``."""
        outer = RuntimeError("")
        inner = ValueError("")
        outer.__cause__ = inner
        assert _message_from_exc(outer) == repr(outer)
