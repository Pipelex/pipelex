from typing import Callable

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.problem import ProblemView
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from tests.unit.pipelex.pipe_controllers.batch.data import PipeBatchInputTestCases


class TestPipeBatchMissingBranch:
    def test_a_branch_pipe_no_bundle_declares_is_refused_naming_the_batch(self, load_empty_library: Callable[[], None]) -> None:
        load_empty_library()
        _, blueprint = PipeBatchInputTestCases.VALID_SIMPLE_BATCH
        pipe_batch = PipeFactory[PipeBatch].make_from_blueprint(domain_code="test_domain", pipe_code="sort_items", blueprint=blueprint)

        with pytest.raises(PipeNotFoundError) as exc_info:
            pipe_batch.required_variables()

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_PIPE_UNRESOLVED
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "sort_items", "missing": "process_item", "candidates": []}
