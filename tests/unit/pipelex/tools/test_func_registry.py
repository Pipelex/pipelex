from collections.abc import Callable
from typing import Any

import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_func_library
from pipelex.libraries.func.exceptions import FuncLibraryError
from pipelex.libraries.func.func_library import FuncLibrary


def sample_function():
    return "sample"


def another_function(x: int):
    return x * 2


# Valid function for testing
def valid_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


# Valid async function for testing (should also be eligible)
async def valid_async_function(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001,RUF029 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


# Invalid functions for testing eligibility
def wrong_param_name(other_param: WorkingMemory) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


def wrong_param_type(working_memory: str) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


def wrong_return_type(working_memory: WorkingMemory) -> str:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return "test"


def too_many_params(working_memory: WorkingMemory, extra: str) -> TextContent:  # noqa: ARG001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


def no_params() -> TextContent:
    return TextContent(text="test")


def no_type_hints(working_memory):  # noqa: ARG001, ANN001 # pyright: ignore[reportUnknownParameterType,reportMissingParameterType, reportUnusedParameter]
    return TextContent(text="test")


# Type alias for test parameters
EligibilityTestCase = tuple[str, Callable[..., Any], bool]

# Test data
TEST_CASES: list[EligibilityTestCase] = [
    # Valid cases
    ("valid_function", valid_function, True),
    ("valid_async_function", valid_async_function, True),
    # Invalid cases
    ("wrong_param_name", wrong_param_name, False),
    ("wrong_param_type", wrong_param_type, False),
    ("wrong_return_type", wrong_return_type, False),
    ("too_many_params", too_many_params, False),
    ("no_params", no_params, False),
    ("no_type_hints", no_type_hints, False),
    ("sample_function", sample_function, False),
    ("another_function", another_function, False),
]


@pytest.fixture
def registry():
    # Create a new registry for each test
    reg = get_func_library()
    yield reg
    # Teardown: clear the registry after each test
    reg.teardown()


class TestFuncLibrary:
    @pytest.mark.parametrize(("test_name", "func", "is_eligible"), TEST_CASES)
    def test_function_eligibility_and_registration(self, registry: FuncLibrary, test_name: str, func: Callable[..., Any], is_eligible: bool):
        # Test eligibility check directly
        actual_eligibility = registry.is_eligible_function(func)
        assert actual_eligibility == is_eligible, f"Eligibility check failed for {test_name}: expected {is_eligible}, got {actual_eligibility}"

        # Test registration behavior
        if is_eligible:
            # Should register successfully
            registry.register_function(func)
            assert registry.has_function(func.__name__), f"Eligible function {test_name} should be registered"
            assert registry.get_function(func.__name__) is func, f"Should be able to retrieve registered function {test_name}"
        else:
            # Should be silently skipped (no error, no registration)
            registry.register_function(func)
            assert not registry.has_function(func.__name__), f"Ineligible function {test_name} should not be registered"

    def test_register_function_with_custom_name(self, registry: FuncLibrary):
        """Test registering a function with a custom name."""
        registry.register_function(valid_function, name="custom_name")
        assert registry.get_function("custom_name") is valid_function
        assert registry.get_function("valid_function") is None

    def test_get_required_function_not_found(self, registry: FuncLibrary):
        with pytest.raises(FuncLibraryError, match="not found in library"):
            registry.get_required_function("non_existent_function")

    def test_unregister_function(self, registry: FuncLibrary):
        registry.register_function(valid_function)
        assert registry.has_function("valid_function")
        registry.unregister_function(valid_function)
        assert not registry.has_function("valid_function")

    def test_unregister_function_not_found(self, registry: FuncLibrary):
        with pytest.raises(FuncLibraryError, match="not found in library"):
            registry.unregister_function(sample_function)

    def test_unregister_function_by_name(self, registry: FuncLibrary):
        registry.register_function(valid_function, name="custom")
        registry.unregister_function_by_name("custom")
        assert not registry.has_function("custom")

    def test_unregister_function_by_name_not_found(self, registry: FuncLibrary):
        with pytest.raises(FuncLibraryError, match="not found in library"):
            registry.unregister_function_by_name("non_existent")

    def test_register_functions_dict_with_ineligible_functions(self, registry: FuncLibrary):
        functions: dict[str, Callable[..., Any]] = {"func1": sample_function, "func2": another_function}
        registry.register_functions_dict(functions)
        # Ineligible functions should be silently skipped
        assert not registry.has_function("func1")
        assert not registry.has_function("func2")
        assert len(registry.root) == 0

    def test_register_functions_list_with_ineligible_functions(self, registry: FuncLibrary):
        functions: list[Callable[..., Any]] = [sample_function, another_function]
        registry.register_functions(functions)
        # Ineligible functions should be silently skipped
        assert not registry.has_function("sample_function")
        assert not registry.has_function("another_function")
        assert len(registry.root) == 0

    def test_register_functions_empty_list(self, registry: FuncLibrary):
        registry.register_functions([])
        assert len(registry.root) == 0

    def test_register_existing_function_replaces(self, registry: FuncLibrary):
        """Test that registering an existing function replaces it without error."""
        registry.register_function(valid_function)
        assert registry.has_function("valid_function")
        # Register again - should not raise
        registry.register_function(valid_function)
        assert registry.has_function("valid_function")

    def test_teardown(self, registry: FuncLibrary):
        registry.register_function(valid_function)
        assert registry.has_function("valid_function")
        registry.teardown()
        assert not registry.has_function("valid_function")

    def test_get_required_function_with_signature(self, registry: FuncLibrary):
        registry.register_function(valid_function)
        func = registry.get_required_function_with_signature("valid_function")
        assert func is valid_function

    def test_get_required_function_with_signature_not_found(self, registry: FuncLibrary):
        with pytest.raises(FuncLibraryError, match="not found in library"):
            registry.get_required_function_with_signature("non_existent")

    def test_get_required_function_with_signature_not_callable(self, registry: FuncLibrary):
        registry.root["not_a_function"] = "a string"  # type: ignore[assignment]
        with pytest.raises(FuncLibraryError, match="is not a callable function"):
            registry.get_required_function_with_signature("not_a_function")
