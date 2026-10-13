import pytest

from pipelex.system.execution_chain import (
    DIRECT_EXECUTION,
    ExecutionAttempt,
    current_chain_keys,
    execution_chain_key,
    make_direct_chain,
)


def _chain(*entries: tuple[str, int]) -> list[ExecutionAttempt]:
    return [ExecutionAttempt(execution=execution, attempt=attempt) for execution, attempt in entries]


class TestExecutionChain:
    def test_the_direct_chain_is_one_execution_in_its_first_attempt(self) -> None:
        assert make_direct_chain() == [ExecutionAttempt(execution=DIRECT_EXECUTION, attempt=1)]

    def test_a_chain_key_tells_every_two_chains_apart(self) -> None:
        assert execution_chain_key(chain=[]) == ""
        assert execution_chain_key(chain=_chain(("exec-run", 1), ("exec-item-2", 3))) == "exec-run@1/exec-item-2@3"
        # An execution's name cannot forge a separator.
        assert execution_chain_key(chain=_chain(("a/b@1", 1))) != execution_chain_key(chain=_chain(("a", 1), ("b", 1)))
        assert execution_chain_key(chain=_chain(("a/b@1", 1))) == "a%2Fb%401@1"

    def test_an_attempt_and_its_lineage_are_validated(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            ExecutionAttempt(execution="exec-run", attempt=0)
        with pytest.raises(ValueError, match="at least 1 character"):
            ExecutionAttempt(execution="", attempt=1)

    def test_a_new_attempt_of_the_run_supersedes_everything_the_earlier_one_dispatched(self) -> None:
        """The worked example, run again: attempt 2 of the run's execution supersedes attempt 1 and every item it dispatched."""
        run_1 = _chain(("exec-run", 1))
        item_2_under_run_1 = _chain(("exec-run", 1), ("exec-item-2", 1))
        item_3_under_run_1 = _chain(("exec-run", 1), ("exec-item-3", 2))
        run_2 = _chain(("exec-run", 2))
        item_1_under_run_2 = _chain(("exec-run", 2), ("exec-item-1", 1))

        current = current_chain_keys(chains=[run_1, item_2_under_run_1, item_3_under_run_1, run_2, item_1_under_run_2, run_1])

        assert current == {execution_chain_key(chain=run_2), execution_chain_key(chain=item_1_under_run_2)}

    def test_a_retried_item_supersedes_only_its_own_earlier_attempts(self) -> None:
        run_1 = _chain(("exec-run", 1))
        item_1 = _chain(("exec-run", 1), ("exec-item-1", 1))
        item_2_first = _chain(("exec-run", 1), ("exec-item-2", 1))
        item_2_second = _chain(("exec-run", 1), ("exec-item-2", 2))
        nested_under_item_2_first = _chain(("exec-run", 1), ("exec-item-2", 1), ("exec-nested", 4))

        current = current_chain_keys(chains=[run_1, item_1, item_2_first, item_2_second, nested_under_item_2_first])

        assert current == {execution_chain_key(chain=chain) for chain in (run_1, item_1, item_2_second)}

    def test_attempts_are_compared_under_the_same_dispatching_attempts_only(self) -> None:
        """An item's attempt 1 under the run's attempt 2 is not superseded by its attempt 3 under the run's attempt 1."""
        item_under_run_1 = _chain(("exec-run", 1), ("exec-item", 3))
        run_2 = _chain(("exec-run", 2))
        item_under_run_2 = _chain(("exec-run", 2), ("exec-item", 1))

        assert current_chain_keys(chains=[item_under_run_1, run_2, item_under_run_2]) == {
            execution_chain_key(chain=run_2),
            execution_chain_key(chain=item_under_run_2),
        }
