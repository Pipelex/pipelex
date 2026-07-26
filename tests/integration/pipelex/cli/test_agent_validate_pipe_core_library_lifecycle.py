"""Library-lifecycle guarantee for the agent-CLI ``_validate_core.validate_pipe_core``.

``validate_pipe_core`` opens a fresh temporary library, makes it current, and drives
``BundleValidator.validate_pipes`` — the D6 inner sweep that NEVER tears the library down. So
``validate_pipe_core`` owns the full lifecycle: on BOTH the success and failure paths it must tear the
temporary library down and restore the caller's outer current-library. Otherwise a long-lived host
that imports it (e.g. the build-assistant sandbox) accumulates libraries and leaves the
current-library ContextVar pointing at a stale validation library (later operations resolve pipes
against the wrong scope). This mirrors the builder twin's guarantee
(``test_validate_pipe_library_lifecycle.py``), which the agent-CLI core previously lacked.

Fully dry (no inference).
"""

import tempfile
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.validate._validate_core import validate_pipe_core  # noqa: PLC2701
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.method_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library

_LIFECYCLE_DOMAIN = "agent_validate_pipe_core_lifecycle"
_LIFECYCLE_MTHDS = f"""
domain = "{_LIFECYCLE_DOMAIN}"
description = "Bundle for validate_pipe_core library-lifecycle tests"

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
class TestAgentValidatePipeCoreLibraryLifecycle:
    async def test_failure_restores_outer_and_tears_down_temp(self, mocker: MockerFixture) -> None:
        # An unknown pipe_code raises PipeNotFoundError after the temporary library was opened + made
        # current. That failure must tear the temporary library down and restore the outer binding.
        library_manager = get_library_manager()
        outer_library_id, _ = library_manager.open_library()
        set_current_library(library_id=outer_library_id)
        open_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        try:
            with pytest.raises(PipeNotFoundError):
                await validate_pipe_core(pipe_code="does_not_exist")
            temp_library_id, _ = open_spy.spy_return
            assert temp_library_id != outer_library_id
            teardown_spy.assert_any_call(library_id=temp_library_id)
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()
            library_manager.teardown(library_id=outer_library_id)

    async def test_success_restores_outer_and_tears_down_temp(self, mocker: MockerFixture) -> None:
        # validate_pipe_core returns a results dict and does not need the library afterward, so a
        # SUCCESSFUL validation must also tear the temporary library down and restore the outer binding.
        library_manager = get_library_manager()
        outer_library_id, _ = library_manager.open_library()
        set_current_library(library_id=outer_library_id)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                (Path(tmp_dir) / "bundle.mthds").write_text(_LIFECYCLE_MTHDS, encoding="utf-8")
                open_spy = mocker.spy(library_manager, "open_library")
                teardown_spy = mocker.spy(library_manager, "teardown")
                result = await validate_pipe_core(
                    pipe_code=f"{_LIFECYCLE_DOMAIN}.summarize_doc",
                    library_dirs=[Path(tmp_dir)],
                )
            assert result["success"] is True
            temp_library_id, _ = open_spy.spy_return
            assert temp_library_id != outer_library_id
            teardown_spy.assert_any_call(library_id=temp_library_id)
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()
            library_manager.teardown(library_id=outer_library_id)
