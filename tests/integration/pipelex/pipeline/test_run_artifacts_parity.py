"""The design's promise: a run's I/O artifact files equal what validate reports for the same bundle.

A results directory and a validate report describe the same method through the same builder and
the same rendering, so for every pipe the validate report knows, the file a run writes holds the
same JSON; and when the run library holds exactly the validated pipes, the files are byte-identical
to what the projection fixture corpus commits for that bundle (the corpus uses the same renderer).

Runs fully dry (`PipeRunMode.DRY` + `mock_inputs`), so no inference happens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.config import get_config
from pipelex.core.pipes.pipe_io_artifacts import (
    INPUT_FORM_FILE_NAME,
    OUTPUT_FORM_FILE_NAME,
    PIPE_IO_CONTRACTS_FILE_NAME,
    PipeIOArtifacts,
    render_pipe_io_artifact_files,
)
from pipelex.graph.graph_config import GraphsInclusionConfig
from pipelex.graph.graph_factory import generate_graph_outputs, save_graph_outputs_to_dir
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PROBE_BUNDLE_PATH = Path(__file__).parents[3] / "data" / "input_semantics" / "probe_bundle.mthds"
_FILE_NAMES = (PIPE_IO_CONTRACTS_FILE_NAME, INPUT_FORM_FILE_NAME, OUTPUT_FORM_FILE_NAME)


def _load(path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


@pytest.mark.asyncio(loop_scope="class")
class TestRunArtifactsParity:
    async def test_a_run_writes_what_validate_reports(self, tmp_path: Path, mocker: MockerFixture) -> None:
        cfg = get_config().runtime.tracing
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(tmp_path / "traces")))
        mthds_content = _PROBE_BUNDLE_PATH.read_text(encoding="utf-8")

        # The run half: execute dry, write the graph outputs the way `pipelex run` does.
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(
            generate_graph=True, generate_usage=False, mock_inputs=True
        )
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute(pipe_code="probe_single", mthds_contents=[mthds_content])
        pipe_output = response.pipe_output
        assert pipe_output.graph_spec is not None
        assert pipe_output.pipe_io_artifacts is not None, pipe_output.pipe_io_artifacts_error
        graph_config = execution_config.graph.model_copy(
            update={
                "graphs_inclusion": GraphsInclusionConfig(graphspec_json=True, mermaidflow_mmd=False, mermaidflow_html=False, reactflow_html=False)
            }
        )
        outputs = await generate_graph_outputs(
            graph_spec=pipe_output.graph_spec, graph_config=graph_config, pipe_io_artifacts=pipe_output.pipe_io_artifacts
        )
        results_dir = tmp_path / "results"
        save_graph_outputs_to_dir(graph_outputs=outputs, output_dir=results_dir)

        # The validate half, rendered through the same function the corpus uses.
        report = await validate_bundles_in_process(mthds_contents=[mthds_content])
        validate_files = render_pipe_io_artifact_files(
            PipeIOArtifacts(pipe_io_contracts=report.pipe_io_contracts, input_form=report.input_form, output_form=report.output_form)
        )

        assert (results_dir / "graphspec.json").is_file()
        for file_name in _FILE_NAMES:
            run_doc = _load(results_dir / file_name)
            validate_doc = json.loads(validate_files[file_name])
            assert validate_doc, f"{file_name}: validate reports at least one pipe"
            for pipe_ref, described in validate_doc.items():
                assert run_doc[pipe_ref] == described, f"{file_name}: the run and validate disagree on {pipe_ref}"
            # Both describe the bundle's own pipes, so the key sets are equal and the bytes must be too;
            # a divergence fails here rather than silently skipping the byte comparison.
            assert set(run_doc) == set(validate_doc), f"{file_name}: the run and validate describe different pipes"
            assert (results_dir / file_name).read_text(encoding="utf-8") == validate_files[file_name], f"{file_name}: not byte-identical"
