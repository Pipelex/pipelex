"""End-to-end optionals showcase from a real `.mthds` bundle file on disk: the lift chain, the
absorbing `?` sink, the `continue` condition, and the `!` force flow all behave per the language
promise when loaded through the normal library-loading path — including the plain-CLI run core
writing the explicit absence artifact.
"""

import json
from pathlib import Path

import pytest

from pipelex.cli.commands.run._run_core import _execute_run  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind
from pipelex.core.pipes.inputs.exceptions import OptionalValueAbsentError
from pipelex.graph.graphspec import NodeStatus
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol

_FIXTURE_DIR = Path(__file__).parent / "optionals_showcase"


def _find_cause(exc: BaseException, *, cause_type: type[BaseException]) -> BaseException | None:
    """Walk the __cause__ chain to find the first exception of the given type."""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, cause_type):
            return current
        current = current.__cause__
    return None


@pytest.mark.asyncio(loop_scope="class")
class TestOptionalsShowcaseE2E:
    async def test_optional_provided_runs_everything_ledger_empty(self):
        """With the optional clause provided and a penalty-bearing contract, nothing lifts: the
        summary rides into the report, the condition takes the flagged branch, and the ledger
        stays empty.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)])

        response = await runner.execute(
            pipe_code="oshow_main_flow",
            inputs={"contract": "contains a penalty clause", "clause": "clause 12"},
        )

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.working_memory.absences == {}
        report_text = response.pipe_output.main_stuff.as_text.text
        assert "summary: analysis of clause 12" in report_text
        assert "Risk: penalty risk detected" in report_text

    async def test_optional_absent_lifts_absorbs_and_records(self):
        """Omitting the optional clause lifts the chain with provenance, the clean contract takes
        the `continue` arm, and the absorbing sink still delivers the main output — with the graph
        marking the lifted pipes as skipped.
        """
        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(generate_graph=True)
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], execution_config=execution_config)

        response = await runner.execute(pipe_code="oshow_main_flow", inputs={"contract": "a clean contract"})

        assert response.state == RunState.COMPLETED
        report_text = response.pipe_output.main_stuff.as_text.text
        assert "No risk assessment." in report_text
        assert "summary: analysis" not in report_text

        memory = response.pipe_output.working_memory
        assert set(memory.absences.keys()) == {"clause", "analysis", "clause_summary", "risk_note"}

        analysis_record = memory.get_optional_absence("analysis")
        assert analysis_record is not None
        assert analysis_record.kind == AbsenceKind.SKIPPED
        assert analysis_record.producing_pipe == "oshow_analyze_clause"
        assert analysis_record.origin().variable_name == "clause"
        assert analysis_record.origin().kind == AbsenceKind.NOT_PROVIDED

        summary_record = memory.get_optional_absence("clause_summary")
        assert summary_record is not None
        assert summary_record.kind == AbsenceKind.SKIPPED
        assert summary_record.producing_pipe == "oshow_summarize_analysis"
        assert summary_record.origin().variable_name == "clause"

        risk_record = memory.get_optional_absence("risk_note")
        assert risk_record is not None
        assert risk_record.kind == AbsenceKind.DECLARED_ABSENT
        assert risk_record.producing_pipe == "oshow_assess_risk"

        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        nodes_by_code = {node.pipe_code: node for node in graph_spec.nodes}
        assert nodes_by_code["oshow_analyze_clause"].status == NodeStatus.SKIPPED
        analyze_skip_reason = nodes_by_code["oshow_analyze_clause"].skip_reason
        assert analyze_skip_reason is not None
        assert "clause" in analyze_skip_reason
        assert nodes_by_code["oshow_summarize_analysis"].status == NodeStatus.SKIPPED
        assert nodes_by_code["oshow_assess_risk"].status == NodeStatus.SUCCEEDED
        assert nodes_by_code["oshow_compose_report"].status == NodeStatus.SUCCEEDED

    async def test_force_flow_absent_raises_typed_error(self):
        """The `!` marker on an absent slot surfaces the typed force error with provenance
        through the pipeline front door.
        """
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)])

        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="oshow_force_flow", inputs={})

        force_error = _find_cause(exc_info.value, cause_type=OptionalValueAbsentError)
        assert isinstance(force_error, OptionalValueAbsentError)
        assert force_error.variable_name == "clause"
        assert force_error.pipe_code == "oshow_force_extract"
        assert force_error.absence_record.origin().kind == AbsenceKind.NOT_PROVIDED

    async def test_force_flow_present_runs(self):
        """With the clause provided, the force marker is satisfied and the flow delivers."""
        runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)])

        response = await runner.execute(pipe_code="oshow_force_flow", inputs={"clause": "clause 12"})

        assert response.state == RunState.COMPLETED
        assert response.pipe_output.main_stuff.as_text.text == "extracted: clause 12"

    async def test_cli_run_core_writes_absence_artifact(self, tmp_path: Path):
        """The unmocked plain-CLI run core, fed the bundle file with the optional omitted, writes
        the explicit absence artifact (json + md, no interactive viewer) and the working memory
        dump carrying the ledger.
        """
        await _execute_run(
            "oshow_lift_only_flow",
            bundle_path=str(_FIXTURE_DIR / "optionals_showcase.mthds"),
            inputs=None,
            save_working_memory=True,
            working_memory_path=None,
            save_main_stuff=True,
            no_pretty_print=True,
            graph=None,
            graph_full_data=None,
            output_dir=str(tmp_path),
            dry_run=False,
            mock_usage=False,
            mock_inputs=False,
            library_dir=None,
        )

        output_dirs = list(tmp_path.glob("oshow_lift_only_flow_output*"))
        assert len(output_dirs) == 1
        output_path = output_dirs[0]

        absence_payload = json.loads((output_path / "main_stuff.json").read_text(encoding="utf-8"))
        assert absence_payload["absent"] is True
        assert absence_payload["variable_name"] == "clause_summary"
        assert (output_path / "main_stuff.md").exists()
        assert not (output_path / "main_stuff_viewer.html").exists()

        memory_dump = json.loads((output_path / "working_memory.json").read_text(encoding="utf-8"))
        assert "clause" in memory_dump["absences"]
