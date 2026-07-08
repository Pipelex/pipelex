"""The open PipeFunc-execution transport DTOs: the generic out-of-process request/response primitive.

These moved from the closed sandbox package into open pipelex so a host runtime (the Temporal
activity) can carry a PipeFunc execution across its boundary without importing any sandbox code. The
response must be JSON-serialization-safe (it crosses the Temporal activity boundary), and the request
must forbid extras (it is a wire contract).
"""

from pipelex.pipe_operators.func.pipe_func_execution_transport import (
    DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
    PipeFuncExecutionRequest,
    PipeFuncExecutionResponse,
)


class TestPipeFuncExecutionTransport:
    def test_response_round_trips_via_json(self) -> None:
        """The transported response survives a JSON round-trip unchanged (it crosses the activity boundary)."""
        response = PipeFuncExecutionResponse(
            output_memory_raw={"main_stuff_name": "result", "stuffs": {}},
            function_module="my_pkg.funcs",
            function_qualname="compute",
        )
        again = PipeFuncExecutionResponse.model_validate_json(response.model_dump_json())
        assert again == response

    def test_request_is_a_forbid_extra_wire_contract_with_default_timeout(self) -> None:
        """The request forbids unknown fields (wire contract) and defaults the runaway-code timeout."""
        assert PipeFuncExecutionRequest.model_config["extra"] == "forbid"
        assert "crate" in PipeFuncExecutionRequest.model_fields
        assert "working_memory_raw" in PipeFuncExecutionRequest.model_fields
        assert PipeFuncExecutionRequest.model_fields["timeout_seconds"].default == DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS
        assert DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS == 5.0
