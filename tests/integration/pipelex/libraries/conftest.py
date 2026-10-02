from collections.abc import Generator

import pytest

from pipelex.config import get_config


@pytest.fixture
def sandbox_hosted_mode() -> Generator[None, None, None]:
    """Select a non-``direct`` execution mode for the duration of a test, then restore it.

    Flipping config (not monkeypatching the helper) exercises the genuine
    is_pipe_func_sandbox_hosted() read at every call site (loader + validators) together: any
    non-``direct`` mode is sandbox-hosted. The concrete sandbox modes live in the out-of-tree closed
    plugin, so this open-core test uses a neutral ``"sandbox"`` token — it only flips the hosted flag
    (the executor already on the hub is never re-resolved here), so no registered mode is needed.
    """
    pipe_func_config = get_config().interpreter.pipe_func
    previous = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "sandbox"
    try:
        yield
    finally:
        pipe_func_config.execution_mode = previous
