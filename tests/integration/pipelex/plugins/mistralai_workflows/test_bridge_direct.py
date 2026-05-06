"""Layer-1 integration tests for the mistralai_workflows bridge in DIRECT mode.

These tests do NOT depend on the optional ``mistralai-workflows`` package — they
exercise only the framework-agnostic core (``run_pipe_via_bridge`` with a real
loaded pipe). The activity wrapper is covered separately in
``test_activities_direct.py``, which DOES require the optional dep.
"""

from typing import Any

import pytest

from pipelex.hub import get_library_manager
from pipelex.plugins.mistralai_workflows.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode

PIPE_REF = "mistralai_workflows_bridge_test.bridge_func_pipe"


@pytest.mark.asyncio(loop_scope="class")
class TestBridgeDirect:
    async def test_direct_mode_with_globally_loaded_library(
        self,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """Bridge runs a pipe found in the active library when no crate is provided."""
        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=PIPE_REF,
                inputs={"input_text": "hello world"},
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert result.is_completed is True
        assert result.workflow_id is None
        assert result.main_stuff_name is not None
        main_stuff_dump = result.output_dict["root"][result.main_stuff_name]
        assert main_stuff_dump["content"]["text"] == "hello world"

    async def test_direct_mode_with_library_crate_dump(
        self,
        bridge_test_library: str,
    ) -> None:
        """Bridge round-trips through ``library_crate_dump`` end-to-end.

        Captures a LibraryCrate from the loaded library, pipes it through the
        bridge as a JSON-safe dict, and verifies the pipe still resolves and
        runs against the per-call scoped library that the bridge opens.
        """
        crate = get_library_manager().get_crate(library_id=bridge_test_library)
        assert crate is not None
        crate_dump: dict[str, Any] = crate.model_dump(mode="json")

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=PIPE_REF,
                inputs={"input_text": "via crate"},
                library_crate_dump=crate_dump,
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert result.is_completed is True
        assert result.main_stuff_name is not None
        main_stuff_dump = result.output_dict["root"][result.main_stuff_name]
        assert main_stuff_dump["content"]["text"] == "via crate"

    async def test_direct_mode_uses_caller_pipeline_run_id(
        self,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """Caller-supplied ``pipeline_run_id`` propagates to the PipeJob."""
        caller_run_id = "caller-supplied-run-id"
        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=PIPE_REF,
                inputs={"input_text": "trace me"},
                pipeline_run_id=caller_run_id,
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert result.is_completed is True
        assert result.pipeline_run_id == caller_run_id
