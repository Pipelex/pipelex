"""Unit tests for ``iter_cause_chain`` — the centralized, cycle-guarded ``__cause__`` walk.

This primitive is load-bearing on the error-reporting path:
``find_inference_error_category_in_chain``, the is-self cycle check in
``_enrich_error_report_from_cause``, ``PipeLLM._format_llm_error`` and the agent-CLI
source-location extraction all delegate to it. A walk that started at ``exc.__cause__``
instead of ``exc`` would silently break the predicates that inspect the seed node, while
that indirect coverage stayed green. These tests pin the two contract properties that
nothing else exercises: the seed is yielded first, and every node is visited exactly once
even on a cyclic chain.
"""

from pipelex.base_exceptions import iter_cause_chain


class TestIterCauseChain:
    def test_yields_seed_first_then_each_cause_in_order(self) -> None:
        """The walk starts at ``exc`` itself, then follows ``__cause__`` outermost-first."""
        leaf = ValueError("leaf")
        middle = RuntimeError("middle")
        outer = RuntimeError("outer")
        middle.__cause__ = leaf
        outer.__cause__ = middle
        assert list(iter_cause_chain(outer)) == [outer, middle, leaf]

    def test_single_exception_yields_only_itself(self) -> None:
        """An exception with no ``__cause__`` yields exactly the seed."""
        exc = RuntimeError("alone")
        assert list(iter_cause_chain(exc)) == [exc]

    def test_self_loop_yields_seed_once(self) -> None:
        """A node that is its own ``__cause__`` terminates after a single yield."""
        exc = RuntimeError("self")
        exc.__cause__ = exc
        assert list(iter_cause_chain(exc)) == [exc]

    def test_two_cycle_yields_each_node_exactly_once(self) -> None:
        """A 2-cycle yields both nodes once, in walk order, without spinning forever."""
        first = RuntimeError("first")
        second = RuntimeError("second")
        first.__cause__ = second
        second.__cause__ = first
        assert list(iter_cause_chain(first)) == [first, second]
