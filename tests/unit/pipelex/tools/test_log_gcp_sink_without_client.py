"""Selecting the ``gcp`` sink without the client library fails at boot naming the extra and the ``json`` alternative.

The dev environment installs every extra, so the subprocess evicts the ``google.cloud.logging``
modules and installs a meta-path finder that refuses to import them again: the next import, the one
the sink's factory performs, is exactly what a missing ``pipelex[gcp-logging]`` would be. A
subprocess, because evicting a package from ``sys.modules`` in the test process would leave duplicate
class objects behind for every later test. The sibling ``google.cloud`` packages are left alone, so
the guard proves the factory's own import is what fails. Modelled on
``test_log_console_sink_without_rich.py``.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap

_GUARD_SCRIPT = textwrap.dedent(
    """
    import importlib.abc
    import sys

    from pipelex.system.exceptions import MissingDependencyError
    from pipelex.tools.log.gcp_log_sink import (
        GCP_LOGGING_DEPENDENCY_NAME,
        GCP_LOGGING_EXTRA_NAME,
        make_gcp_log_sink,
    )
    from pipelex.tools.log.log_config import GcpLogSinkConfig

    BLOCKED_PREFIXES = ("google.cloud.logging", "google.cloud.logging_v2")

    def is_blocked(fullname):
        return any(fullname == prefix or fullname.startswith(f"{prefix}.") for prefix in BLOCKED_PREFIXES)

    for name in [module for module in sys.modules if is_blocked(module)]:
        del sys.modules[name]

    class _Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if is_blocked(fullname):
                raise ImportError(f"no-cloud-logging guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _Blocker())

    try:
        make_gcp_log_sink(config=GcpLogSinkConfig(log_name="pipelex"))
    except MissingDependencyError as exc:
        message = str(exc)
        assert exc.dependency_name == GCP_LOGGING_DEPENDENCY_NAME, message
        assert exc.extra_name == GCP_LOGGING_EXTRA_NAME, message
        assert f"pipelex[{GCP_LOGGING_EXTRA_NAME}]" in message, message
        assert "json" in message, message
        print("fails loud OK")
    else:
        raise SystemExit("expected MissingDependencyError from the gcp sink without the client library")
    """
)


class TestGcpLogSinkWithoutClient:
    def test_gcp_sink_fails_loud_naming_the_extra_and_the_json_alternative(self) -> None:
        result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", _GUARD_SCRIPT],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, f"no-cloud-logging guard failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "fails loud OK" in result.stdout
