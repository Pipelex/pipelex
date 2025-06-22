from typing import Any, Callable, Dict, List

import pytest
from pytest import LogCaptureFixture

from pipelex.tools.func_registry import FuncRegistry, FuncRegistryError


def sample_function():
    return "sample"


def another_function(x: int):
    return x * 2


@pytest.fixture
def registry():
    # Create a new registry for each test
    reg = FuncRegistry()
    yield reg
    # Teardown: clear the registry after each test
    reg.teardown()


class TestFuncRegistry:
    def test_register_and_get_function(self, registry: FuncRegistry):
        registry.register_function(sample_function)
        assert registry.get_function("sample_function") is sample_function

    def test_register_function_with_custom_name(self, registry: FuncRegistry):
        registry.register_function(sample_function, name="custom_name")
        assert registry.get_function("custom_name") is sample_function
        assert registry.get_function("sample_function") is None

    def test_has_function(self, registry: FuncRegistry):
        registry.register_function(sample_function)
        assert registry.has_function("sample_function")
        assert not registry.has_function("non_existent_function")

    def test_get_required_function(self, registry: FuncRegistry):
        registry.register_function(sample_function)
        assert registry.get_required_function("sample_function") is sample_function

    def test_get_required_function_not_found(self, registry: FuncRegistry):
        with pytest.raises(FuncRegistryError, match="not found in registry"):
            registry.get_required_function("non_existent_function")

    def test_unregister_function(self, registry: FuncRegistry):
        registry.register_function(sample_function)
        assert registry.has_function("sample_function")
        registry.unregister_function(sample_function)
        assert not registry.has_function("sample_function")

    def test_unregister_function_not_found(self, registry: FuncRegistry):
        with pytest.raises(FuncRegistryError, match="not found in registry"):
            registry.unregister_function(sample_function)

    def test_unregister_function_by_name(self, registry: FuncRegistry):
        registry.register_function(sample_function, name="custom")
        registry.unregister_function_by_name("custom")
        assert not registry.has_function("custom")

    def test_unregister_function_by_name_not_found(self, registry: FuncRegistry):
        with pytest.raises(FuncRegistryError, match="not found in registry"):
            registry.unregister_function_by_name("non_existent")

    def test_register_functions_dict(self, registry: FuncRegistry):
        functions: Dict[str, Callable[..., Any]] = {"func1": sample_function, "func2": another_function}
        registry.register_functions_dict(functions)
        assert registry.get_function("func1") is sample_function
        assert registry.get_function("func2") is another_function

    def test_register_functions_list(self, registry: FuncRegistry):
        functions: List[Callable[..., Any]] = [sample_function, another_function]
        registry.register_functions(functions)
        assert registry.get_function("sample_function") is sample_function
        assert registry.get_function("another_function") is another_function

    def test_register_functions_empty_list(self, registry: FuncRegistry):
        registry.register_functions([])
        assert len(registry.root) == 0

    def test_register_existing_function_with_warning(self, registry: FuncRegistry, caplog: LogCaptureFixture):
        registry.register_function(sample_function)
        with caplog.at_level("DEBUG"):
            registry.register_function(sample_function)
        assert "already exists in registry" in caplog.text

    def test_register_existing_function_no_warning(self, registry: FuncRegistry, caplog: LogCaptureFixture):
        registry.register_function(sample_function)
        with caplog.at_level("DEBUG"):
            registry.register_function(sample_function, should_warn_if_already_registered=False)
        assert "already exists in registry" not in caplog.text

    def test_teardown(self, registry: FuncRegistry):
        registry.register_function(sample_function)
        assert registry.has_function("sample_function")
        registry.teardown()
        assert not registry.has_function("sample_function")

    def test_get_required_function_with_signature(self, registry: FuncRegistry):
        registry.register_function(another_function)
        func = registry.get_required_function_with_signature("another_function", another_function)
        assert func is another_function

    def test_get_required_function_with_signature_not_found(self, registry: FuncRegistry):
        with pytest.raises(FuncRegistryError, match="not found in registry"):
            registry.get_required_function_with_signature("non_existent", sample_function)

    def test_get_required_function_with_signature_not_callable(self, registry: FuncRegistry):
        registry.root["not_a_function"] = "a string"  # type: ignore
        with pytest.raises(FuncRegistryError, match="is not a callable function"):
            registry.get_required_function_with_signature("not_a_function", sample_function)
