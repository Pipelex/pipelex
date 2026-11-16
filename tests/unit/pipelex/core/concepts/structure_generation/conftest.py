from collections.abc import Iterator

import pytest

from tests.unit.pipelex.core.concepts.structure_generation.statement_probe import STATEMENTS_RUN


@pytest.fixture
def clear_statements_run() -> Iterator[None]:
    """Empty `STATEMENTS_RUN` before and after the test, so each test sees only the statements it ran."""
    STATEMENTS_RUN.clear()
    yield
    STATEMENTS_RUN.clear()
