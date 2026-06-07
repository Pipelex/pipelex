from collections.abc import Generator
from pathlib import Path

import pytest

from pipelex.hub import get_func_registry, get_library_manager, set_current_library
from tests.integration.pipelex.runtime_bridge.test_data.bridge_funcs import (
    mistralai_workflows_bridge_echo,
    mistralai_workflows_bridge_raise,
)

TEST_DATA_DIR = Path(__file__).parent / "test_data"


@pytest.fixture(scope="class")
def bridge_test_library() -> Generator[str, None, None]:
    """Open a class-scoped library populated with the bridge test pipe.

    The pipe ``mistralai_workflows_bridge_test.bridge_func_pipe`` is registered
    in the active library, and the matching Python function is registered in
    the FuncRegistry. Both are torn down on exit.
    """
    func_registry = get_func_registry()
    func_registry.register_function(mistralai_workflows_bridge_echo)
    func_registry.register_function(mistralai_workflows_bridge_raise)

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    library_manager.load_libraries(
        library_id=library_id,
        library_dirs=[TEST_DATA_DIR],
    )
    try:
        yield library_id
    finally:
        library_manager.teardown(library_id=library_id)
        for func_name in ("mistralai_workflows_bridge_echo", "mistralai_workflows_bridge_raise"):
            if func_registry.has_function(func_name):
                func_registry.unregister_function_by_name(func_name)
