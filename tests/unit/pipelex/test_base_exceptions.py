import subprocess  # noqa: S404
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

        ``ErrorReport`` is constructed directly with literal ``title`` / ``type_uri``
        (instead of via ``PipelexConfigError(...).to_error_report()`` which would call
        ``type_uri()`` -> ``get_config()`` and fail in this no-bootstrap subprocess —
        a separate test exercises that path with config loaded).
        """
        code = (
            "import sys\n"
            "from pipelex.base_exceptions import ErrorReport\n"
            "assert 'pipelex.cogt.exceptions' not in sys.modules, "
            "'cogt.exceptions already loaded — test no longer exercises the cold path'\n"
            "direct = ErrorReport(error_type='X', message='m', "
            "title='X error', type_uri='https://pipelex.dev/errors/x')\n"
            "assert direct.to_dict() == {'error_type': 'X', 'message': 'm', "
            "'title': 'X error', 'type_uri': 'https://pipelex.dev/errors/x'}\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
        assert result.returncode == 0, f"cold-path ErrorReport construction failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
