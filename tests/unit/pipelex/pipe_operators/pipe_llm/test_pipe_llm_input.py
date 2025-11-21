from typing import Callable

import pytest

from pipelex import log
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory
from tests.unit.pipelex.pipe_operators.pipe_llm.data import PipeLLMInputTestCases


class TestPipeLLMValidateInputs:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeLLMInputTestCases.VALID_CASES,
    )
    def test_validate_inputs_valid_cases(
        self,
        test_id: str,
        blueprint: PipeLLMBlueprint,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        log.verbose(f"Testing valid case: {test_id}")

        pipe_llm = PipeLLMFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        pipe_llm.validate_inputs_static()
        pipe_llm.validate_inputs_with_library()
