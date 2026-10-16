import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys


class TestErrorReportColdImport:
    def test_error_report_constructable_without_cogt_exceptions_loaded(self):
        """``ErrorReport`` must be fully defined without importing ``pipelex.cogt.exceptions``.

        Regression: ``ErrorReport``'s ``user_action`` / ``provider_metadata`` fields
        were forward references resolved only by a ``rebuild_dataclass()`` call living
        in ``pipelex.cogt.exceptions``. Any cold path that built an error report before
        that module happened to load raised ``PydanticUserError`` — error reporting
        itself crashed. Runs in a subprocess so a clean interpreter is guaranteed; the
        in-process pytest session has already imported ``cogt`` and would mask the bug.

        ``ErrorReport`` is constructed both directly, with literal ``code`` / ``title`` /
        ``type_uri``, and from a code through ``ErrorReport.make_for_code``, which reads
        the registry's generated tables and so needs no bootstrap either.
        """
        code = (
            "import sys\n"
            "from pipelex.base_exceptions import ErrorReport\n"
            "assert 'pipelex.cogt.exceptions' not in sys.modules, "
            "'cogt.exceptions already loaded — test no longer exercises the cold path'\n"
            "direct = ErrorReport(code='runtime.unexpected', error_type='X', message='m', "
            "title='X error', type_uri='https://mthds.ai/errors/runtime.unexpected')\n"
            "assert direct.to_dict() == {'code': 'runtime.unexpected', 'error_type': 'X', 'message': 'm', "
            "'title': 'X error', 'type_uri': 'https://mthds.ai/errors/runtime.unexpected'}\n"
            "from mthds.protocol.problem.registry import CoreCode\n"
            "coded = ErrorReport.make_for_code(code=CoreCode.RUNTIME_UNEXPECTED, error_type='X', message='m')\n"
            "assert coded.type_uri == 'https://mthds.ai/errors/runtime.unexpected'\n"
            "assert 'pipelex.cogt.exceptions' not in sys.modules\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
        assert result.returncode == 0, f"cold-path ErrorReport construction failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
