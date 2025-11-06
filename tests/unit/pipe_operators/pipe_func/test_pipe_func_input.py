import pytest

from pipelex import log
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_factory import PipeFuncFactory
from pipelex.system.registries.func_registry import func_registry
from tests.unit.pipe_operators.pipe_func.data import ERROR_TEST_FUNCTIONS, PipeFuncInputTestCases


@pytest.fixture(scope="class")
def register_error_test_functions():
    """Register error test functions that have validation issues.

    These functions have intentional validation issues (no return type, wrong return type)
    and need to be registered bypassing normal eligibility checks to test validation logic.
    They are properly cleaned up after the test class completes.
    """
    registered_names: list[str] = []

    # Register each error test function
    # Note: We use register_function first (which will skip ineligible functions),
    # then manually add if needed for testing validation
    for func_name, func in ERROR_TEST_FUNCTIONS.items():
        # Try normal registration first
        func_registry.register_function(func, name=func_name)

        # If not registered (due to eligibility check), manually add for testing
        if not func_registry.has_function(func_name):
            # Directly add to registry for testing validation (intentionally bypassing checks)
            func_registry.root[func_name] = func

        registered_names.append(func_name)

    yield registered_names

    # Cleanup: use proper accessor to unregister all error test functions
    for func_name in registered_names:
        if func_registry.has_function(func_name):
            func_registry.unregister_function_by_name(func_name)


@pytest.mark.usefixtures("register_error_test_functions")
class TestPipeFuncValidation:
    @pytest.mark.parametrize(
        ("test_id", "blueprint"),
        PipeFuncInputTestCases.VALID_CASES,
    )
    def test_pipe_func_validate_valid_cases(
        self,
        test_id: str,
        blueprint: PipeFuncBlueprint,
    ):
        log.verbose(f"Testing valid case: {test_id}")

        pipe_func = PipeFuncFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code=f"test_pipe_{test_id}",
            blueprint=blueprint,
        )

        # Assert that the pipe was created successfully
        assert pipe_func is not None
        assert pipe_func.code == f"test_pipe_{test_id}"
        assert pipe_func.function_name == blueprint.function_name

    @pytest.mark.parametrize(
        ("test_id", "blueprint", "expected_error_substring"),
        PipeFuncInputTestCases.ERROR_CASES,
    )
    def test_pipe_func_validate_error_cases(
        self,
        test_id: str,
        blueprint: PipeFuncBlueprint,
        expected_error_substring: str,
    ):
        log.verbose(f"Testing error case: {test_id}")

        # Assert that creating the pipe raises PipeDefinitionError
        with pytest.raises(PipeDefinitionError) as exc_info:
            PipeFuncFactory.make_from_blueprint(
                domain="test_domain",
                pipe_code=f"test_pipe_{test_id}",
                blueprint=blueprint,
            )

        # Assert that the error message contains the expected substring
        error_message = str(exc_info.value)
        assert expected_error_substring in error_message, f"Expected error message to contain '{expected_error_substring}', but got: {error_message}"
