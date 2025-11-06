from typing import ClassVar

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from tests.unit.core.test_data.complex.multi_feature import COMPLEX_TEST_CASES
from tests.unit.core.test_data.concepts.refining_concepts import REFINING_CONCEPT_TEST_CASES
from tests.unit.core.test_data.concepts.simple_concepts import SIMPLE_CONCEPT_TEST_CASES
from tests.unit.core.test_data.concepts.structured_concepts import STRUCTURED_CONCEPT_TEST_CASES
from tests.unit.core.test_data.domain.simple_domains import DOMAIN_TEST_CASES
from tests.unit.core.test_data.errors.invalid_plx import ERROR_TEST_CASES
from tests.unit.core.test_data.pipes.controllers.batch.pipe_batch import PIPE_BATCH_TEST_CASES
from tests.unit.core.test_data.pipes.controllers.condition.pipe_condition import PIPE_CONDITION_TEST_CASES
from tests.unit.core.test_data.pipes.controllers.parallel.pipe_parallel import PIPE_PARALLEL_TEST_CASES
from tests.unit.core.test_data.pipes.controllers.sequence.pipe_sequence import PIPE_SEQUENCE_TEST_CASES
from tests.unit.core.test_data.pipes.operators.compose.pipe_compose import PIPE_COMPOSE_TEST_CASES
from tests.unit.core.test_data.pipes.operators.extract.pipe_extract import PIPE_EXTRACT_TEST_CASES
from tests.unit.core.test_data.pipes.operators.func.pipe_func import PIPE_FUNC_TEST_CASES
from tests.unit.core.test_data.pipes.operators.img_gen.pipe_img_gen import PIPE_IMG_GEN_TEST_CASES
from tests.unit.core.test_data.pipes.operators.llm.pipe_llm import PIPE_LLM_TEST_CASES


class InterpreterTestCases:
    """Test cases for PipelexInterpreter with PLX content and expected blueprints."""

    # Aggregate all valid test cases from organized modules
    VALID_TEST_CASES: ClassVar[list[tuple[str, str, PipelexBundleBlueprint]]] = [  # test_name,plx_content,blueprint
        # Domain tests
        *DOMAIN_TEST_CASES,
        # Concept tests
        *STRUCTURED_CONCEPT_TEST_CASES,
        *REFINING_CONCEPT_TEST_CASES,
        *SIMPLE_CONCEPT_TEST_CASES,
        # Pipe operator tests
        *PIPE_LLM_TEST_CASES,
        *PIPE_EXTRACT_TEST_CASES,
        *PIPE_FUNC_TEST_CASES,
        *PIPE_IMG_GEN_TEST_CASES,
        *PIPE_COMPOSE_TEST_CASES,
        # Pipe controller tests
        *PIPE_SEQUENCE_TEST_CASES,
        *PIPE_CONDITION_TEST_CASES,
        *PIPE_PARALLEL_TEST_CASES,
        *PIPE_BATCH_TEST_CASES,
        # Complex tests
        *COMPLEX_TEST_CASES,
    ]

    # Error test cases
    ERROR_TEST_CASES: ClassVar[list[tuple[str, str, type[Exception] | tuple[type[Exception], ...]]]] = ERROR_TEST_CASES
