"""A run's NDJSON trace states each controller decision before the work under it, and every event states its mode.

The trace is read as a reader tailing the file would read it: line by line, in the order the run wrote it. A condition's
resolution comes before the first event of the pipe it chose, a batch's fan-out before the first event of its items, a
sequence and a parallel state their width on their own start, and every line says whether the run is live or dry.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_mock import MockerFixture

import pipelex.pipeline.pipeline_run_setup as pipeline_run_setup_module
from pipelex.config import get_config
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.ndjson_event_log import NdjsonEventLog

if TYPE_CHECKING:
    from pipelex.pipe_run.pipe_job import PipeJob

_DOMAIN = "decisions_at_decision_time"
_BUNDLE = f"""
domain = "{_DOMAIN}"
description = "Route a request, answer every ticket of an inbox, then weigh the outcome two ways"
main_pipe = "triage"

[concept.Ticket]
description = "A support ticket"

[concept.Ticket.structure]
subject = {{ type = "text", description = "What the ticket is about", required = true }}

[concept.Inbox]
description = "An inbox of support tickets"

[concept.Inbox.structure]
tickets = {{ type = "list", item_type = "concept", item_concept_ref = "Ticket", description = "The tickets", required = true }}

[pipe.triage]
type = "PipeSequence"
description = "Route, answer each ticket, weigh, conclude"
inputs = {{ request = "Text", inbox = "Inbox" }}
output = "Text"
steps = [
  {{ pipe = "route", result = "routed" }},
  {{ pipe = "answer_ticket", batch_over = "inbox.tickets", batch_as = "ticket", result = "answers" }},
  {{ pipe = "weigh", result = "weighed" }},
  {{ pipe = "conclude", result = "conclusion" }},
]

[pipe.route]
type = "PipeCondition"
description = "Escalate an urgent request, file any other"
inputs = {{ request = "Text" }}
output = "Text"
expression = "request"
outcomes = {{ urgent = "escalate" }}
default_outcome = "file_away"

[pipe.escalate]
type = "PipeCompose"
description = "Escalate the request"
inputs = {{ request = "Text" }}
output = "Text"
template = "Escalated: {{{{ request }}}}"

[pipe.file_away]
type = "PipeCompose"
description = "File the request"
inputs = {{ request = "Text" }}
output = "Text"
template = "Filed: {{{{ request }}}}"

[pipe.answer_ticket]
type = "PipeCompose"
description = "Answer one ticket"
inputs = {{ ticket = "Ticket" }}
output = "Text"
template = "Answer to {{{{ ticket.subject }}}}"

[pipe.weigh]
type = "PipeParallel"
description = "Weigh the routed request two ways at once"
inputs = {{ routed = "Text" }}
output = "Composite"
add_each_output = true
branches = [
  {{ pipe = "weigh_short", result = "short_view" }},
  {{ pipe = "weigh_long", result = "long_view" }},
]

[pipe.weigh_short]
type = "PipeCompose"
description = "The short view"
inputs = {{ routed = "Text" }}
output = "Text"
template = "Short: {{{{ routed }}}}"

[pipe.weigh_long]
type = "PipeCompose"
description = "The long view"
inputs = {{ routed = "Text" }}
output = "Text"
template = "Long: {{{{ routed }}}}"

[pipe.conclude]
type = "PipeCompose"
description = "Conclude on both views and the answers"
inputs = {{ short_view = "Text", long_view = "Text", answers = "Text[]" }}
output = "Text"
template = "{{{{ short_view }}}} / {{{{ long_view }}}} / {{{{ answers }}}}"
"""

_INBOX = {"tickets": [{"subject": "Login"}, {"subject": "Billing"}]}


def _read_trace_lines(traces_dir: Path) -> list[dict[str, Any]]:
    """Every line of the run's one NDJSON file, in the order the run wrote them."""
    ndjson_files = list(traces_dir.rglob("*.ndjson"))
    assert len(ndjson_files) == 1, ndjson_files
    return [json.loads(line) for line in ndjson_files[0].read_text(encoding="utf-8").splitlines() if line.strip()]


def _descendants(*, lines: list[dict[str, Any]], node_id: str) -> set[str]:
    """The node IDs of every pipe started under `node_id`, at any depth."""
    children_by_parent: dict[str, list[str]] = {}
    for line in lines:
        if line["event_kind"] == "pipe_start" and line["parent_node_id"] is not None:
            children_by_parent.setdefault(line["parent_node_id"], []).append(line["node_id"])
    found: set[str] = set()
    pending = [node_id]
    while pending:
        for child_id in children_by_parent.get(pending.pop(), []):
            found.add(child_id)
            pending.append(child_id)
    return found


def _first_line_under(*, lines: list[dict[str, Any]], node_id: str) -> int:
    """The position of the first line naming a pipe started under `node_id`: its start, an edge into it, or its data."""
    under = _descendants(lines=lines, node_id=node_id)
    assert under, f"nothing ran under {node_id}"
    return min(
        position
        for position, line in enumerate(lines)
        if line.get("node_id") in under or line.get("target_node_id") in under or line.get("batch_controller_node_id") in under
    )


def _one(*, lines: list[dict[str, Any]], event_kind: str) -> tuple[int, dict[str, Any]]:
    found = [(position, line) for position, line in enumerate(lines) if line["event_kind"] == event_kind]
    assert len(found) == 1, f"{event_kind}: {found}"
    return found[0]


def _starts_by_code(lines: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    starts: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        if line["event_kind"] == "pipe_start":
            starts.setdefault(line["pipe_code"], []).append(line)
    return starts


@pytest.mark.asyncio(loop_scope="class")
class TestDecisionsAtDecisionTime:
    @pytest.mark.parametrize(
        ("request_text", "selected_outcome", "chosen_pipe_code"),
        [("urgent", "urgent", "escalate"), ("routine", None, "file_away")],
        ids=["matched_key", "default_outcome"],
    )
    async def test_live_trace_states_each_decision_before_the_work_under_it(
        self, tmp_path: Path, request_text: str, selected_outcome: str | None, chosen_pipe_code: str
    ) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(execution_config=execution_config)

        with scoped_event_log(NdjsonEventLog(traces_dir=str(tmp_path))):
            response = await runner.execute(
                mthds_contents=[_BUNDLE],
                inputs={"request": request_text, "inbox": {"concept": f"{_DOMAIN}.Inbox", "content": _INBOX}},
            )

        prefix = "Escalated" if chosen_pipe_code == "escalate" else "Filed"
        assert response.pipe_output.main_stuff.as_text.text.startswith(f"Short: {prefix}: {request_text} / Long: {prefix}: {request_text} / ")
        lines = _read_trace_lines(tmp_path)

        # Every line states the run's mode, and so does the graph built from them.
        assert {line["mode"] for line in lines} == {"live"}
        assert response.pipe_output.graph_spec is not None
        assert response.pipe_output.graph_spec.meta["mode"] == "live"

        # The condition's resolution precedes the first event of the pipe it chose.
        resolution_position, resolution = _one(lines=lines, event_kind="condition_resolved")
        starts = _starts_by_code(lines)
        route_start = starts["route"][0]
        assert resolution["node_id"] == route_start["node_id"]
        assert resolution["rendered_value"] == request_text
        assert resolution["selected_outcome"] == selected_outcome
        assert resolution_position < _first_line_under(lines=lines, node_id=route_start["node_id"])
        chosen_start = starts[chosen_pipe_code][0]
        assert chosen_start["parent_node_id"] == route_start["node_id"]
        # The graph built from those events draws the choice as its SELECTED_OUTCOME edge, labelled with the key.
        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        assert [(edge.source, edge.target, edge.label) for edge in graph_spec.edges if edge.kind.is_selected_outcome] == [
            (route_start["node_id"], chosen_start["node_id"], selected_outcome)
        ]

        # The batch's fan-out precedes the first event of its items.
        fan_out_position, fan_out = _one(lines=lines, event_kind="batch_fanned_out")
        batch_start = next(line for line in lines if line["event_kind"] == "pipe_start" and line["node_id"] == fan_out["node_id"])
        assert batch_start["pipe_type"] == "PipeBatch"
        assert (fan_out["item_count"], fan_out["branch_pipe_code"], fan_out["branch_pipe_ref"], fan_out["branch_pipe_type"]) == (
            2,
            "answer_ticket",
            f"{_DOMAIN}.answer_ticket",
            "PipeCompose",
        )
        assert fan_out_position < _first_line_under(lines=lines, node_id=fan_out["node_id"])
        assert len(starts["answer_ticket"]) == 2

        # A sequence states the steps its author wrote, the binding of the dotted `batch_over` not among them, and a
        # parallel its branches, each on its own start; no other pipe states either.
        assert (starts["triage"][0]["step_count"], starts["triage"][0]["branch_count"]) == (4, None)
        assert (starts["weigh"][0]["step_count"], starts["weigh"][0]["branch_count"]) == (None, 2)
        for pipe_code, code_starts in starts.items():
            if pipe_code not in {"triage", "weigh"}:
                assert all(start["step_count"] is None and start["branch_count"] is None for start in code_starts), pipe_code

    async def test_dry_trace_states_its_mode_and_resolves_no_condition(self, tmp_path: Path) -> None:
        """A dry run runs every outcome of a condition and chooses none, so it records no resolution."""
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True, mock_inputs=True)
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)

        with scoped_event_log(NdjsonEventLog(traces_dir=str(tmp_path))):
            response = await runner.execute(mthds_contents=[_BUNDLE])

        lines = _read_trace_lines(tmp_path)
        assert {line["mode"] for line in lines} == {"dry"}
        assert [line for line in lines if line["event_kind"] == "condition_resolved"] == []
        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        assert graph_spec.meta["mode"] == "dry"
        assert [edge for edge in graph_spec.edges if edge.kind.is_selected_outcome] == []
        starts = _starts_by_code(lines)
        assert starts["triage"][0]["step_count"] == 4
        assert starts["weigh"][0]["branch_count"] == 2

    async def test_a_live_request_on_a_keyless_boot_is_dry_throughout(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A keyless boot runs a requested live run dry: its job, its trace context, every event and its graph all say dry."""
        mocker.patch("pipelex.runtime_hub.is_dry_run_forced", return_value=True)
        prepare_pipe_job_spy = mocker.spy(pipeline_run_setup_module, "prepare_pipe_job")
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE, execution_config=execution_config)

        with scoped_event_log(NdjsonEventLog(traces_dir=str(tmp_path))):
            response = await runner.execute(
                mthds_contents=[_BUNDLE],
                inputs={"request": "urgent", "inbox": {"concept": f"{_DOMAIN}.Inbox", "content": _INBOX}},
            )

        pipe_job: PipeJob = prepare_pipe_job_spy.spy_return
        assert pipe_job.pipe_run_params.run_mode.is_dry
        trace_context = pipe_job.job_metadata.trace_context
        assert trace_context is not None
        assert trace_context.run_mode.is_dry
        lines = _read_trace_lines(tmp_path)
        assert {line["mode"] for line in lines} == {"dry"}
        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        assert graph_spec.meta["mode"] == "dry"
        # The pipes ran dry too: the condition ran every outcome and resolved none.
        assert [line for line in lines if line["event_kind"] == "condition_resolved"] == []

    async def test_a_keyless_boot_still_refuses_mock_usage_on_a_live_request(self, mocker: MockerFixture) -> None:
        """The requested mode is validated before the keyless coercion, so it cannot legalise mock usage on a live request."""
        mocker.patch("pipelex.runtime_hub.is_dry_run_forced", return_value=True)
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE, is_mock_usage=True)

        with pytest.raises(ValueError, match="is_mock_usage"):
            await runner.execute(mthds_contents=[_BUNDLE], inputs={"request": "urgent"})
