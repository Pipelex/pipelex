from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def restore_current_library() -> Iterator[None]:
    """A command whose teardown is patched out leaves its library open and current: tear it down and restore the outer one."""
    outer_library_id = get_current_library_id_or_none()
    yield
    current_library_id = get_current_library_id_or_none()
    if current_library_id is not None and current_library_id != outer_library_id:
        get_library_manager().teardown(library_id=current_library_id)
    if outer_library_id is not None:
        set_current_library(library_id=outer_library_id)
    else:
        clear_current_library()
