"""The open PipeFunc-execution transport DTOs: the generic out-of-process request/response primitive.

These moved from the closed sandbox package into open pipelex so a host runtime (the Temporal
activity) can carry a PipeFunc execution across its boundary without importing any sandbox code. The
response must be JSON-serialization-safe (it crosses the Temporal activity boundary), and the request
must forbid extras (it is a wire contract).
"""

import pytest
from mthds.method_tree.file_entry import Base64FileEntry
from pydantic import ValidationError

from pipelex.core.method_trees.tree_files import tree_file_bytes
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func.pipe_func_execution_transport import (
    DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
    PipeFuncExecutionRequest,
    PipeFuncExecutionResponse,
)
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


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
        assert PipeFuncExecutionRequest.model_config.get("extra") == "forbid"
        assert "crate" in PipeFuncExecutionRequest.model_fields
        assert "working_memory_raw" in PipeFuncExecutionRequest.model_fields
        assert PipeFuncExecutionRequest.model_fields["timeout_seconds"].default == DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS

    def test_request_carries_the_call_files_as_file_entries(self) -> None:
        """The call's files travel at their tree paths, text as text and other bytes in Base64, and survive a JSON round-trip."""
        binary = bytes([0, 159, 146, 150])
        request = PipeFuncExecutionRequest(
            crate=LibraryCrate(),
            files={"funcs/totals.py": "TOTAL = 3\n", "assets/logo.bin": Base64FileEntry.make_from_bytes(binary)},
            working_memory_raw={},
            pipe_code="my_domain.my_pipe",
            function_name="funcs.totals.compute_totals",
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )
        again = PipeFuncExecutionRequest.model_validate_json(request.model_dump_json())
        assert tree_file_bytes(entry=again.files["funcs/totals.py"]) == b"TOTAL = 3\n"
        assert tree_file_bytes(entry=again.files["assets/logo.bin"]) == binary

    def test_request_rejects_non_finite_timeout(self) -> None:
        """A non-finite timeout would disable the runaway-code guard, so the wire contract rejects it."""
        with pytest.raises(ValidationError, match="timeout_seconds"):
            PipeFuncExecutionRequest(
                crate=LibraryCrate(),
                working_memory_raw={},
                pipe_code="my_pipe",
                function_name="my_funcs.my_func",
                job_metadata=JobMetadata(
                    run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")
                ),
                pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
                timeout_seconds=float("inf"),
            )
