"""Layer-1 integration tests for the runtime-bridge in DIRECT mode.

These tests do NOT depend on any host-runtime optional package — they
exercise only the framework-agnostic core (``run_pipe_via_bridge`` with a
real loaded pipe). The Mistral Workflows activity wrapper is covered
separately in the ``pipelex-mistralai-workflows`` package, which DOES
require the optional dep.
"""

import json
from typing import Any

import pytest
from kajson.kajson_manager import KajsonManager

from pipelex.hub import get_current_library_id_or_none, get_library_manager
from pipelex.runtime_bridge.bridge import PipelexPipeRunInput, run_pipe_via_bridge
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode

PIPE_REF = "mistralai_workflows_bridge_test.bridge_func_pipe"
ENVELOPE_PIPE_REF = "mistralai_workflows_bridge_test.bridge_envelope_pipe"
RAISE_PIPE_REF = "mistralai_workflows_bridge_test.bridge_raise_pipe"


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
        # Usage fields exist on the boundary DTO (None here — this run does no inference
        # and opens no tracer, so the cost-assembly path produces nothing).
        assert result.tokens_usages_dump is None
        assert result.usage_assembly_error is None

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

    async def test_direct_mode_dynamic_concept_round_trips_via_library_crate_dump(
        self,
        bridge_test_library: str,
    ) -> None:
        """A concept with an inline structure round-trips through ``library_crate_dump``.

        ``EchoEnvelope`` is defined inline in the bridge_test bundle. The bridge
        dehydrates the library to a JSON-safe crate dump, opens a per-call
        scoped library on the receiving side, and re-hydrates the concept so
        ``PipeCompose`` can construct a ``StructuredContent`` matching the
        dynamic shape.
        """
        envelope_pipe_ref = "mistralai_workflows_bridge_test.bridge_envelope_pipe"
        crate = get_library_manager().get_crate(library_id=bridge_test_library)
        assert crate is not None
        crate_dump: dict[str, Any] = crate.model_dump(mode="json")

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=envelope_pipe_ref,
                inputs={"input_text": "wrapped"},
                library_crate_dump=crate_dump,
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert result.is_completed is True
        assert result.main_stuff_name is not None
        main_stuff = result.output_dict["root"][result.main_stuff_name]
        content = main_stuff["content"]
        assert content["text"] == "wrapped"
        assert content["origin"] == "mistralai_workflows_bridge"

    async def test_crate_run_restores_prior_current_library(
        self,
        bridge_test_library: str,
    ) -> None:
        """A crate-scoped bridge run restores the caller's current library on exit.

        The bridge opens a per-call scoped library for the crate. When it
        returns, the previously active library (the fixture's) must be restored,
        not cleared — otherwise a later no-crate bridge call in the same async
        context could no longer resolve pipes.
        """
        assert get_current_library_id_or_none() == bridge_test_library

        crate = get_library_manager().get_crate(library_id=bridge_test_library)
        assert crate is not None
        crate_dump: dict[str, Any] = crate.model_dump(mode="json")

        await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=PIPE_REF,
                inputs={"input_text": "restore me"},
                library_crate_dump=crate_dump,
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert get_current_library_id_or_none() == bridge_test_library

    async def test_direct_mode_wraps_user_code_exception_in_dispatch_error(
        self,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """A non-Pipelex exception from user pipe code surfaces as PipelexBridgeDispatchError.

        The PipeFunc operator wraps the user function's ValueError into a
        PipeRunError, which the bridge converts to its boundary error type — so a
        raw ValueError never escapes the bridge across the host-runtime seam.
        """
        with pytest.raises(PipelexBridgeDispatchError):
            await run_pipe_via_bridge(
                PipelexPipeRunInput(
                    pipe_code=RAISE_PIPE_REF,
                    inputs={"input_text": "boom"},
                    execution_mode=PipelexExecutionMode.DIRECT,
                )
            )

    async def test_crate_inline_concept_does_not_leak_into_global_registry(
        self,
        bridge_test_library: str,
    ) -> None:
        """Classes generated from a crate's inline concepts stay out of the global registry.

        The bridge loads the crate into a per-call scoped ``ClassRegistry`` so a
        long-lived / multi-tenant host doesn't accumulate (or collide on) dynamic
        concept classes across crate versions. We rename the bundle's inline
        ``EchoEnvelope`` concept to a probe name that has never been loaded
        globally, so any presence in the global registry afterwards is
        unambiguously a leak from the bridge's crate path.
        """
        crate = get_library_manager().get_crate(library_id=bridge_test_library)
        assert crate is not None
        crate_dump: dict[str, Any] = crate.model_dump(mode="json")
        probe_dump: dict[str, Any] = json.loads(json.dumps(crate_dump).replace("EchoEnvelope", "EchoEnvelopeProbe"))

        global_registry = KajsonManager.get_class_registry()
        before = set(global_registry.get_classes_dict().keys())
        assert not any("EchoEnvelopeProbe" in name for name in before), "Probe class must not be globally loaded before the run"

        result = await run_pipe_via_bridge(
            PipelexPipeRunInput(
                pipe_code=ENVELOPE_PIPE_REF,
                inputs={"input_text": "probe"},
                library_crate_dump=probe_dump,
                execution_mode=PipelexExecutionMode.DIRECT,
            )
        )

        assert result.is_completed is True
        after = set(global_registry.get_classes_dict().keys())
        leaked = {name for name in (after - before) if "EchoEnvelopeProbe" in name}
        assert not leaked, f"Crate-generated class(es) leaked into the global Kajson registry: {leaked}"
