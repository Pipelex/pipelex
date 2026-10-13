import json
from pathlib import Path
from typing import Any

import pytest

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.graph.graphspec import GraphSpec, NodeStatus
from pipelex.interpreter_hub import scoped_pipe_router
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import PipeEndErrorEvent, PipeStartEvent, TraceEvent
from tests.integration.pipelex.pipeline.invocation_paths.invocation_paths_helpers import ItemExecutionRouter
from tests.integration.pipelex.pipeline.invocation_paths.test_data import InvocationPathsTestData

_BINDING_PIPE_TYPE = "BindingStep"


def _read_trace_lines(traces_dir: Path) -> list[dict[str, Any]]:
    """Every line the run wrote, file by file, each file in the order it was written."""
    lines: list[dict[str, Any]] = []
    for ndjson_file in sorted(traces_dir.rglob("*.ndjson")):
        lines.extend(json.loads(line) for line in ndjson_file.read_text(encoding="utf-8").splitlines() if line.strip())
    return lines


def _concerned_node_id(line: dict[str, Any]) -> str:
    """The node an event is about, whose path it carries."""
    node_id: str
    match line["event_kind"]:
        case "edge":
            node_id = line["target_node_id"]
        case "batch_item" | "batch_aggregate":
            node_id = line["batch_controller_node_id"]
        case "parallel_combine":
            node_id = line["parallel_controller_node_id"]
        case "condition_output_merge":
            node_id = line["merge"]["condition_node_id"]
        case _:
            node_id = line["node_id"]
    return node_id


def _invocation_paths(lines: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """By path, the code and type of the pipe each invocation start names, refusing two starts at one path."""
    paths: dict[str, tuple[str, str]] = {}
    for line in lines:
        if line["event_kind"] != "pipe_start" or line["path"] is None:
            continue
        assert line["path"] not in paths, f"two starts at {line['path']}"
        paths[line["path"]] = (line["pipe_code"], line["pipe_type"])
    return paths


def _graph_paths(graph_spec: GraphSpec | None) -> list[str]:
    assert graph_spec is not None
    return sorted(node.path for node in graph_spec.nodes if node.path is not None)


async def _run(*, depth: str, run_mode: PipeRunMode, traces_dir: Path) -> PipeOutput:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True, mock_inputs=run_mode.is_dry)
    runner = PipelexMTHDSProtocol(pipe_run_mode=run_mode, execution_config=execution_config)
    inputs: dict[str, Any] | None = None
    if not run_mode.is_dry:
        inputs = {"depth": depth, "dossier": {"concept": f"{InvocationPathsTestData.DOMAIN}.Dossier", "content": InvocationPathsTestData.DOSSIER}}
    with scoped_event_log(NdjsonEventLog(traces_dir=str(traces_dir))):
        response = await runner.execute(mthds_contents=[InvocationPathsTestData.BUNDLE], inputs=inputs)
    return response.pipe_output


@pytest.mark.asyncio(loop_scope="class")
class TestInvocationPaths:
    async def test_every_event_of_a_live_run_carries_the_path_of_the_worked_example(self, tmp_path: Path) -> None:
        pipe_output = await _run(depth="detailed", run_mode=PipeRunMode.LIVE, traces_dir=tmp_path)

        lines = _read_trace_lines(tmp_path)
        assert _invocation_paths(lines) == InvocationPathsTestData.LIVE_DETAILED_PATHS
        # One execution in its first attempt wrote them all.
        assert {(line["workflow_id"], line["attempt"], json.dumps(line["lineage"])) for line in lines} == {("direct", 1, "[]")}

        # The binding the runtime writes for the dotted `batch_over` runs no pipe and takes no path, and leaves the
        # batch it was written for the number of the author's step.
        binding_starts = [line for line in lines if line["event_kind"] == "pipe_start" and line["pipe_type"] == _BINDING_PIPE_TYPE]
        assert [(start["pipe_code"], start["path"], start["pipe_ref"]) for start in binding_starts] == [("dossier.filings", None, None)]

        # Every event carries the path of the invocation it is about, and an invocation's start names its pipe.
        path_by_node_id = {line["node_id"]: line["path"] for line in lines if line["event_kind"] == "pipe_start"}
        for line in lines:
            assert line["path"] == path_by_node_id[_concerned_node_id(line)], line
            if line["event_kind"] == "pipe_start" and line["path"] is not None:
                assert line["pipe_ref"] == f"{InvocationPathsTestData.DOMAIN}.{line['pipe_code']}"
            if line["event_kind"] == "pipe_end_success":
                ended_path: str | None = line["path"]
                expected_pipe = (
                    (line["pipe_code"], _BINDING_PIPE_TYPE) if ended_path is None else InvocationPathsTestData.LIVE_DETAILED_PATHS[ended_path]
                )
                assert (line["pipe_code"], line["pipe_type"]) == expected_pipe

        # Item `n` of the batch is the filing at index `n - 1`.
        for item_number, filing in enumerate(InvocationPathsTestData.DOSSIER["filings"], start=1):
            read_end = next(
                line
                for line in lines
                if line["event_kind"] == "pipe_end_success"
                and line["path"] == f"{InvocationPathsTestData.ENTRY_PATH}/step_3/item_{item_number}/step_1"
            )
            assert filing["title"] in json.dumps(read_end), read_end

        # The graph names each invocation by the same path.
        assert _graph_paths(pipe_output.graph_spec) == sorted(InvocationPathsTestData.LIVE_DETAILED_PATHS)

    @pytest.mark.parametrize(
        ("depth", "chosen_pipe_code"),
        [
            ("detailed", "deep_checks"),
            ("high risk", "deep_checks"),
            ("quick", "quick_check"),
            ("routine", "quick_check"),
            ("legal/tax review", "legal_check"),
        ],
        ids=["first_key_of_a_group", "second_key_of_a_group", "key_sharing_the_default_pipe", "default_outcome", "key_needing_encoding"],
    )
    async def test_a_condition_runs_each_outcome_group_at_one_path(self, tmp_path: Path, depth: str, chosen_pipe_code: str) -> None:
        """The outcomes running one pipe form one group, named by its first key, whichever of them a live run takes."""
        await _run(depth=depth, run_mode=PipeRunMode.LIVE, traces_dir=tmp_path)

        outcome_starts = [
            (path, pipe_code)
            for path, (pipe_code, _) in _invocation_paths(_read_trace_lines(tmp_path)).items()
            if path.startswith(f"{InvocationPathsTestData.ENTRY_PATH}/step_2/") and path.count("/") == 2
        ]
        assert outcome_starts == [(InvocationPathsTestData.OUTCOME_GROUP_PATHS[chosen_pipe_code], chosen_pipe_code)]

    async def test_a_dry_run_names_each_pipe_by_the_path_a_live_run_gives_it(self, tmp_path: Path) -> None:
        """A dry run runs every outcome group of the condition, each at the path a live run taking it gives."""
        pipe_output = await _run(depth="detailed", run_mode=PipeRunMode.DRY, traces_dir=tmp_path)

        lines = _read_trace_lines(tmp_path)
        assert {line["mode"] for line in lines} == {"dry"}
        dry_paths = _invocation_paths(lines)
        for pipe_code, group_path in InvocationPathsTestData.OUTCOME_GROUP_PATHS.items():
            assert dry_paths[group_path][0] == pipe_code
        live_paths_outside_the_items = {path: pipe for path, pipe in InvocationPathsTestData.LIVE_DETAILED_PATHS.items() if "/item_" not in path}
        assert live_paths_outside_the_items.items() <= dry_paths.items()
        # The dry batch's items are numbered from 1 as the live batch's are, each running the same pipes.
        item_numbers = sorted(int(path.split("/item_")[1]) for path in dry_paths if path.count("/") == 2 and "/item_" in path)
        assert item_numbers == list(range(1, len(item_numbers) + 1))
        assert item_numbers
        assert dry_paths[f"{InvocationPathsTestData.ENTRY_PATH}/step_3/item_1/step_2"] == ("condense_filing", "PipeFunc")
        assert _graph_paths(pipe_output.graph_spec) == sorted(dry_paths)

    async def test_an_item_run_as_an_execution_of_its_own_continues_the_path_it_received(self, tmp_path: Path) -> None:
        """Each item runs as an execution of its own, from a job read back from its serialized form, and the engine runs
        one of them twice: both attempts stamp the same paths under the prefix the item received, the graph keeps the
        later one, and no node of the lost attempt shows as failed.
        """
        router = ItemExecutionRouter(retried_item_segment="item_2")
        with scoped_pipe_router(router):
            pipe_output = await _run(depth="detailed", run_mode=PipeRunMode.LIVE, traces_dir=tmp_path)

        batch_path = f"{InvocationPathsTestData.ENTRY_PATH}/step_3"
        run_attempt = ExecutionAttempt(execution="direct", attempt=1)
        # The job each item's execution read back carries the item's place and the attempt that dispatched it.
        assert sorted(router.received_contexts) == ["item_1", "item_2", "item_3"]
        for item_segment, received_context in router.received_contexts.items():
            assert (received_context.parent_path, received_context.child_segment) == (batch_path, item_segment)
            assert received_context.chain == [run_attempt]

        events: list[TraceEvent] = NdjsonEventLog(traces_dir=str(tmp_path)).read_events(pipe_output.pipeline_run_id)
        item_starts: dict[tuple[str, int], set[str]] = {}
        for event in events:
            if event.workflow_id == "direct":
                assert (event.attempt, event.lineage) == (1, [])
                continue
            # An item's execution stamps the lineage it was dispatched under, and only paths under the one it received.
            item_segment = event.workflow_id.removeprefix("exec-")
            assert event.lineage == [run_attempt]
            assert event.path is not None
            assert event.path == f"{batch_path}/{item_segment}" or event.path.startswith(f"{batch_path}/{item_segment}/")
            if isinstance(event, PipeStartEvent):
                item_starts.setdefault((item_segment, event.attempt), set()).add(event.path)
        # The two attempts of item 2 share their paths.
        assert sorted(item_starts) == [("item_1", 1), ("item_2", 1), ("item_2", 2), ("item_3", 1)]
        assert (
            item_starts["item_2", 1]
            == item_starts["item_2", 2]
            == {
                f"{batch_path}/item_2",
                f"{batch_path}/item_2/step_1",
                f"{batch_path}/item_2/step_2",
            }
        )
        lost_failures = [event for event in events if isinstance(event, PipeEndErrorEvent) and event.workflow_id == "exec-item_2"]
        assert {(event.attempt, event.path) for event in lost_failures} >= {(1, f"{batch_path}/item_2/step_2")}

        # The graph holds every invocation once, from the current attempts, and nothing of the lost attempt failed in it.
        graph_spec = pipe_output.graph_spec
        assert _graph_paths(graph_spec) == sorted(InvocationPathsTestData.LIVE_DETAILED_PATHS)
        assert graph_spec is not None
        assert [node.path for node in graph_spec.nodes if node.status == NodeStatus.FAILED] == []
        main_text = pipe_output.main_stuff.as_text.text
        for filing in InvocationPathsTestData.DOSSIER["filings"]:
            assert f"Condensed: Read {filing['title']}" in main_text

    async def test_a_binding_step_the_author_wrote_takes_its_number(self, tmp_path: Path) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config)
        with scoped_event_log(NdjsonEventLog(traces_dir=str(tmp_path))):
            await runner.execute(
                mthds_contents=[InvocationPathsTestData.BOUND_STEP_BUNDLE],
                inputs={"filing": {"concept": "bound_steps.Filing", "content": {"title": "Annual accounts"}}},
            )

        lines = _read_trace_lines(tmp_path)
        assert _invocation_paths(lines) == {
            "bound_steps.label_filing": ("label_filing", "PipeSequence"),
            "bound_steps.label_filing/step_2": ("write_label", "PipeCompose"),
        }
        binding_starts = [line for line in lines if line["event_kind"] == "pipe_start" and line["pipe_type"] == _BINDING_PIPE_TYPE]
        assert [(start["pipe_code"], start["path"]) for start in binding_starts] == [("filing.title", None)]
