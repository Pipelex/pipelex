import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipelexInterpreterParallelPLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Basic Parallel pipe
            (
                "parallel_process",
                PipeParallelBlueprint(
                    type="PipeParallel",
                    definition="Process data in parallel",
                    output="ProcessedData",
                    parallels=[
                        SubPipeBlueprint(pipe="process_a", result="result_a"),
                        SubPipeBlueprint(pipe="process_b", result="result_b"),
                    ],
                ),
                """[pipe.parallel_process]
type = "PipeParallel"
definition = "Process data in parallel"
output = "ProcessedData"
parallels = [
    { pipe = "process_a", result = "result_a" },
    { pipe = "process_b", result = "result_b" },
]""",
            ),
            # Parallel pipe with inputs and options
            (
                "complex_parallel",
                PipeParallelBlueprint(
                    type="PipeParallel",
                    definition="Complex parallel processing",
                    inputs={"data": "Text"},
                    output="ProcessedData",
                    parallels=[
                        SubPipeBlueprint(pipe="analyze", result="analysis"),
                        SubPipeBlueprint(pipe="summarize", result="summary"),
                        SubPipeBlueprint(pipe="extract", result="extraction"),
                    ],
                    add_each_output=False,
                    combined_output="MergedResults",
                ),
                """[pipe.complex_parallel]
type = "PipeParallel"
definition = "Complex parallel processing"
inputs = { data = "Text" }
output = "ProcessedData"
parallels = [
    { pipe = "analyze", result = "analysis" },
    { pipe = "summarize", result = "summary" },
    { pipe = "extract", result = "extraction" },
]
add_each_output = false
combined_output = "MergedResults\"""",
            ),
        ],
    )
    def test_parallel_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeParallelBlueprint, expected_plx: str):
        result = PipelexInterpreter.parallel_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
