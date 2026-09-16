"""Selecting the ``console`` sink without Rich installed fails at boot naming the extra and the ``json`` alternative.

Rich is a hard dependency today and the runtime's own modules import it, so the subprocess evicts every
``rich`` module and installs a meta-path finder that refuses to import it again: the next import, the one
the sink's ``make_handler`` performs, is exactly what an uninstalled Rich would be. A subprocess, because
evicting a package from ``sys.modules`` in the test process would leave duplicate class objects behind
for every later test. Modelled on ``test_import_light_boot.py``.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap

_GUARD_SCRIPT = textwrap.dedent(
    """
    import importlib.abc
    import sys

    from pipelex.system.console_target import ConsoleTarget
    from pipelex.system.exceptions import MissingDependencyError
    from pipelex.tools.log.console_log_sink import RICH_EXTRA_NAME, ConsoleLogSink
    from pipelex.tools.log.log_config import HighlighterName, RichLogConfig

    for name in [module for module in sys.modules if module == "rich" or module.startswith("rich.")]:
        del sys.modules[name]

    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "rich" or fullname.startswith("rich."):
                raise ImportError(f"no-rich guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _Blocker())

    sink = ConsoleLogSink(
        rich_log_config=RichLogConfig(
            is_show_time=False,
            is_show_level=True,
            is_link_path_enabled=True,
            highlighter_name=HighlighterName.JSON,
            is_markup_enabled=True,
            is_rich_tracebacks=True,
            is_tracebacks_word_wrap=True,
            is_tracebacks_show_locals=False,
            tracebacks_suppress=[],
            keywords_to_hilight=[],
        ),
        target=ConsoleTarget.STDERR,
    )
    try:
        sink.handler
    except MissingDependencyError as exc:
        message = str(exc)
        assert exc.dependency_name == "rich", message
        assert exc.extra_name == RICH_EXTRA_NAME, message
        assert f"pipelex[{RICH_EXTRA_NAME}]" in message, message
        assert "json" in message, message
        print("fails loud OK")
    else:
        raise SystemExit("expected MissingDependencyError from the console sink without Rich")
    """
)


class TestConsoleLogSinkWithoutRich:
    def test_console_sink_fails_loud_naming_the_extra_and_the_json_alternative(self) -> None:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _GUARD_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, f"no-rich guard failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "fails loud OK" in result.stdout
