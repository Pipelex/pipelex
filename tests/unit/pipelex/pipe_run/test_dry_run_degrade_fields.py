from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.pipe_run.dry_run_in_process import best_effort_graph_spec

DRY_RUN_MODULE = "pipelex.pipe_run.dry_run_in_process"


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunDegradeFields:
    @pytest.mark.parametrize(
        ("topic", "is_resolved", "target", "expected_pipe_fields"),
        [
            (
                "a pipe named by its reference",
                True,
                "company.describe_company",
                {"pipe_code": "describe_company", "pipe_ref": "company.describe_company"},
            ),
            ("a pipe named by its bare code", True, "describe_company", {"pipe_code": "describe_company", "pipe_ref": "company.describe_company"}),
            ("a qualified target that resolves to no pipe", False, "company.missing_pipe", {"pipe_ref": "company.missing_pipe"}),
            ("a bare target that resolves to no pipe", False, "missing_pipe", {"pipe_code": "missing_pipe"}),
        ],
    )
    async def test_the_degrade_warning_names_the_pipe_as_the_pipe_run_lines_do(
        self, mocker: MockerFixture, topic: str, is_resolved: bool, target: str, expected_pipe_fields: dict[str, Any]
    ) -> None:
        """`pipe_code` carries the bare code `Pipe run starts` carries, and a qualified reference rides `pipe_ref`."""
        pipe = mocker.MagicMock()
        pipe.code = "describe_company"
        pipe.pipe_ref = "company.describe_company"
        pipe_library = mocker.patch(f"{DRY_RUN_MODULE}.get_library_manager").return_value.get_library.return_value.pipe_library
        if is_resolved:
            pipe_library.get_required_entry_pipe.return_value = pipe
            mocker.patch(f"{DRY_RUN_MODULE}.dry_run_pipe_in_process", new=mocker.AsyncMock(side_effect=PipelexError("the dry run failed")))
        else:
            pipe_library.get_required_entry_pipe.side_effect = PipelexError("no such pipe")
        log_spy = mocker.patch(f"{DRY_RUN_MODULE}.log")

        graph_spec = await best_effort_graph_spec(pipe_ref=target, library_id="library-1", log_context="test_caller")

        assert graph_spec is None, topic
        log_spy.warning.assert_called_once()
        fields = log_spy.warning.call_args.kwargs["fields"]
        assert {key: value for key, value in fields.items() if key in {"pipe_code", "pipe_ref"}} == expected_pipe_fields, topic
        assert fields["caller"] == "test_caller", topic
        assert fields["error.type"] == "PipelexError", topic
