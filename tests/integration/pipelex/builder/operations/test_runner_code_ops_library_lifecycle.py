"""Failure-path library-lifecycle guarantee for ``runner_code_ops.build_runner_code_for_pipe``.

On SUCCESS the function intentionally leaves the library open + current — the D6 loaded-on-success
contract, pinned by ``test_validate_bundle_loaded_on_success`` (the caller resolves + generates code
against the still-open library, then tears it down). On FAILURE this caller owns cleanup: a raise
after the temporary library is opened + current (e.g. an unknown ``pipe_code`` →
``PipeNotFoundError`` from ``get_required_pipe``, after the bundle itself validates) must restore the
caller's outer current-library and tear the temporary library down, or a long-lived builder/API
process leaks one library per failed request.

Fully dry (no inference).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.builder.operations.runner_code_ops import build_runner_code_for_pipe
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.method_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library

_RC_DOMAIN = "runner_code_lifecycle"
_RC_MTHDS = f"""
domain = "{_RC_DOMAIN}"
description = "Bundle for runner_code_ops failure-path lifecycle test"

[concept.Doc]
description = "A document"

[pipe.summarize_doc]
type = "PipeLLM"
description = "Summarize a document"
inputs = {{ doc = "Doc" }}
output = "Text"
prompt = "Summarize $doc"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerCodeOpsLibraryLifecycle:
    async def test_failure_restores_outer_and_tears_down_temp(self, mocker: MockerFixture) -> None:
        # The bundle validates fine, but the requested pipe_code is absent -> get_required_pipe raises
        # PipeNotFoundError AFTER the temporary library was opened + made current. That failure must not
        # leak the library nor leave it current.
        library_manager = get_library_manager()
        outer_library_id, _ = library_manager.open_library()
        set_current_library(library_id=outer_library_id)
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        try:
            with pytest.raises(PipeNotFoundError):
                await build_runner_code_for_pipe(mthds_contents=[_RC_MTHDS], pipe_code="does_not_exist")
            temp_library_id, _ = open_spy.spy_return
            assert temp_library_id != outer_library_id
            teardown_spy.assert_any_call(library_id=temp_library_id)
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()
            library_manager.teardown(library_id=outer_library_id)
