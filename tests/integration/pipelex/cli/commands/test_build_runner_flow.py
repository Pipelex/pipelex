"""Integration: `pipelex build runner` core flow over a real bundle (validate -> emit -> script).

Pins the D9 re-point: the runner scaffold's structures/ output comes from the codegen engine (one
stamped structures.py + codegen.lock), and the generated script spells custom classes the way the
emitted module defines them (bare-when-unique), importing them from `structures.structures`.
"""

import ast
import tempfile
from pathlib import Path

import pytest

from pipelex.cli.commands.build.runner._runner_core import _prepare_runner_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME
from pipelex.hub import clear_current_library, get_current_library, get_library_manager

_BUNDLE_MTHDS = """\
domain = "runnerflow"
description = "Runner-flow test domain"
main_pipe = "answer_query"

[concept.Query]
description = "A user query"
structure.question = { description = "the question", type = "text", required = true }

[concept.Report]
description = "A report"
structure.summary = { description = "the summary", type = "text", required = true }

[pipe.answer_query]
type = "PipeLLM"
description = "Answer a query with a report"
inputs = { query = "Query" }
output = "Report"
model = "$quick-reasoning"
prompt = "Answer $query"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestBuildRunnerFlow:
    async def test_runner_and_structures_projection_agree_on_names(self):
        """The emitted structures.py defines bare-when-unique classes and the runner script imports
        and instantiates exactly those spellings (no runtime-qualified names leak into the script).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir)
            bundle_path = bundle_dir / "bundle.mthds"
            bundle_path.write_text(_BUNDLE_MTHDS, encoding="utf-8")

            try:
                await _prepare_runner_core(pipe_code=None, bundle_path=bundle_path, library_dirs=[bundle_dir])
            finally:
                # validate_bundle leaves its library open and current (loaded-on-success); the CLI
                # wrapper tears the whole Pipelex down, so the test cleans up the library itself.
                library_id = get_current_library()
                clear_current_library()
                get_library_manager().teardown(library_id=library_id)

            structures_file = bundle_dir / "structures" / "structures.py"
            assert structures_file.is_file()
            assert (bundle_dir / "structures" / CODEGEN_LOCK_FILENAME).is_file()
            structures_code = structures_file.read_text(encoding="utf-8")
            assert "class Query(StructuredContent):" in structures_code
            assert "class Report(StructuredContent):" in structures_code

            runner_file = bundle_dir / "run_answer_query.py"
            assert runner_file.is_file()
            runner_code = runner_file.read_text(encoding="utf-8")
            ast.parse(runner_code)

            # Imports come from the single emitted module, spelled bare-when-unique.
            assert "from structures.structures import Query" in runner_code
            assert "from structures.structures import Report" in runner_code
            # The example input instantiates the emitted class; the output cast uses it too.
            assert "Query(question=" in runner_code
            assert "pipe_output.main_stuff_as(content_type=Report)" in runner_code
            # No runtime-qualified spelling leaks into the script.
            assert "runnerflow__" not in runner_code
