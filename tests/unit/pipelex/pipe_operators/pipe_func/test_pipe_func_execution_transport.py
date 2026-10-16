"""The open PipeFunc-execution transport DTOs: the generic out-of-process request/response primitive.

These moved from the closed sandbox package into open pipelex so a host runtime (the Temporal
activity) can carry a PipeFunc execution across its boundary without importing any sandbox code. The
response must be JSON-serialization-safe (it crosses the Temporal activity boundary), and the request
must forbid extras (it is a wire contract).
"""

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.method_trees.tree_bundle import TreeBundleRef
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_operators.func.pipe_func_execution_transport import (
    DEFAULT_PIPE_FUNC_TIMEOUT_SECONDS,
    PipeFuncExecutionRequest,
    PipeFuncExecutionResponse,
    build_pipe_func_execution_request,
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

    def test_request_names_the_tree_of_the_called_step_by_digest_and_carries_no_file(self) -> None:
        """The call's files are read through the method file store by whoever runs it, so the request names the tree only."""
        tree_digest = "sha256:" + "b" * 64
        request = PipeFuncExecutionRequest(
            crate=LibraryCrate(tree_bundles={"my_domain.my_pipe": TreeBundleRef(tree_digest=tree_digest, tree_path="main.mthds")}),
            tree_digest=tree_digest,
            working_memory_raw={},
            pipe_code="my_domain.my_pipe",
            function_name="funcs.totals.compute_totals",
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        again = PipeFuncExecutionRequest.model_validate_json(request.model_dump_json())

        assert again.tree_digest == tree_digest
        assert "files" not in PipeFuncExecutionRequest.model_fields

    @pytest.mark.parametrize("in_a_tree", [True, False], ids=["step-in-a-tree", "step-in-no-tree"])
    def test_the_built_request_names_the_tree_the_crate_names_for_the_step(self, mocker: MockerFixture, in_a_tree: bool) -> None:
        tree_digest = "sha256:" + "c" * 64
        tree_bundles = {"my_domain.my_pipe": TreeBundleRef(tree_digest=tree_digest, tree_path=None)} if in_a_tree else {}
        mocker.patch("pipelex.pipe_operators.func.pipe_func_execution_transport.get_current_library", return_value="library")
        library_manager = mocker.MagicMock()
        library_manager.get_crate.return_value = LibraryCrate(tree_bundles=tree_bundles)
        mocker.patch("pipelex.pipe_operators.func.pipe_func_execution_transport.get_library_manager", return_value=library_manager)

        request = build_pipe_func_execution_request(
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")),
            pipe_code="my_domain.my_pipe",
            function_name="funcs.totals.compute_totals",
            working_memory=WorkingMemory(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
        )

        assert request.tree_digest == (tree_digest if in_a_tree else None)

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
