import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys


class TestProblemColdImport:
    def test_a_problem_is_built_without_cogt_exceptions_loaded(self):
        """A problem is built from an error, or from a code alone, without importing ``pipelex.cogt.exceptions``.

        Regression: the error document's fields were once forward references resolved only by a rebuild living in
        ``pipelex.cogt.exceptions``, so any cold path that reported an error before that module happened to load
        crashed while reporting it. Runs in a subprocess so a clean interpreter is guaranteed; the in-process pytest
        session has already imported ``cogt`` and would mask the bug.

        The problem is built both from a ``PipelexError``, in the operator's view, and from a code through
        ``make_problem``, which reads the registry's generated tables and so needs no bootstrap either.
        """
        code = (
            "import sys\n"
            "from mthds.protocol.problem.registry import CoreCode\n"
            "from pipelex.base_exceptions import PipelexError\n"
            "from pipelex.errors.problem import ProblemView, make_problem\n"
            "assert 'pipelex.cogt.exceptions' not in sys.modules, "
            "'cogt.exceptions already loaded — test no longer exercises the cold path'\n"
            "operator = PipelexError('m').to_problem(view=ProblemView.OPERATOR).to_wire()\n"
            "assert operator['code'] == 'runtime.unexpected', operator\n"
            "assert operator['type'] == 'https://mthds.ai/errors/runtime.unexpected', operator\n"
            "assert operator['diagnostics']['error_class'] == 'PipelexError', operator\n"
            "assert operator['diagnostics']['message'] == 'm', operator\n"
            "coded = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER).to_wire()\n"
            "assert coded == {'type': 'https://mthds.ai/errors/runtime.unexpected', 'title': 'An unexpected error occurred', "
            "'detail': 'The runtime met an unexpected error.', 'code': 'runtime.unexpected', 'domain': 'runtime', 'retry': 'no', "
            "'next_step': {'kind': 'report', 'detail': 'Report this to whoever runs the runtime.'}}, coded\n"
            "assert 'pipelex.cogt.exceptions' not in sys.modules\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
        assert result.returncode == 0, f"cold-path problem construction failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
