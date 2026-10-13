from collections.abc import Iterator

import pytest

from pipelex.system.registries.func_registry import func_registry
from tests.integration.pipelex.pipeline.invocation_paths.invocation_paths_helpers import invocation_paths_condense_filing


@pytest.fixture(autouse=True)
def register_condense_filing() -> Iterator[None]:
    """Register the function the worked example's `condense_filing` runs, for the test's duration."""
    func_registry.register_function(invocation_paths_condense_filing)
    yield
    if func_registry.has_function(invocation_paths_condense_filing.__name__):
        func_registry.unregister_function_by_name(invocation_paths_condense_filing.__name__)
