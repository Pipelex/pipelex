from __future__ import annotations

import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import textwrap
from pathlib import Path

import pytest

from pipelex.tools.misc.pretty import PrettyPrintMode
from pipelex.tools.misc.rich_extra import RICH_EXTRA_NAME

#: Anchored on `tests/` by name rather than by a parent count, for the reason `test_hub_layering_guard.py` gives.
_REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests").parent

# Rich is the `cli` extra, and a server installs pipelex without it. The suite installs every extra, so the
# subprocess stands in for that install: a meta-path finder installed before the first `pipelex` import
# refuses every `rich` module, which is exactly what an uninstalled Rich is to an `import`. A subprocess,
# because the test process has Rich loaded already and evicting it would leave duplicate classes behind.
_NO_RICH_PRELUDE = textwrap.dedent(
    """
    import importlib.abc
    import sys

    class _RichBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "rich" or fullname.startswith("rich."):
                raise ImportError(f"no-rich guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _RichBlocker())

    from pipelex.pipelex import Pipelex
    from pipelex.system.runtime import IntegrationMode

    # A pytest-spawned process, and it says so. The session's run mode is set on the in-process
    # `runtime_manager` and never exported, so a child can neither read it nor claim `IntegrationMode.CI`
    # on the strength of it; what keeps these boots credential-free is `needs_model_specs=False` below,
    # not the mode.
    INTEGRATION_MODE = IntegrationMode.PYTEST
    """
)

# A live run of an operator pipe that needs no inference, in-process, so the "Output of pipe" panel every
# operator prints is on the path. Rich must still be absent from the process when the run is over.
#
# `needs_model_specs=False` is what makes the boot runnable on a machine that has never configured
# inference — a CI runner, that is. The bundle below names no model, so the Pipelex service's published
# specs are of no use to it: the boot takes the dummy-specs branch, which asks for neither the gateway
# terms nor the network. `needs_inference` stays True on purpose — a keyless boot forces every run to DRY,
# and the dry path does not print the "Output of pipe" panel, which is the Rich reach under test.
_RUN_SCRIPT = _NO_RICH_PRELUDE + textwrap.dedent(
    """
    import asyncio

    from pipelex.pipeline.runner import PipelexMTHDSProtocol

    BUNDLE = '''
    domain = "rich_free_run"
    description = "A compose pipe, which needs no inference"
    main_pipe = "greet"

    [pipe.greet]
    type = "PipeCompose"
    description = "Greet the name"
    inputs = { name = "Text" }
    output = "Text"
    template = "Hello {{ name }}!"
    '''

    Pipelex.make(
        integration_mode=INTEGRATION_MODE,
        needs_model_specs=False,
        config_overrides={"runtime": {"log": {"sink": "json", "pretty_print_mode": sys.argv[1]}}},
    )
    result = asyncio.run(PipelexMTHDSProtocol().execute(mthds_contents=[BUNDLE], inputs={"name": {"concept": "Text", "content": "world"}}))
    assert result.pipe_output.main_stuff_as_str == "Hello world!", result.pipe_output.main_stuff_as_str
    Pipelex.teardown_if_needed()
    loaded = sorted(name for name in sys.modules if name == "rich" or name.startswith("rich."))
    assert not loaded, loaded
    print("rich-free run OK")
    """
)

# The pretty-print mode "rich" needs Rich: a boot without it stops at boot, naming the extra and the
# Rich-free modes, rather than at the first pipe that prints its output. `needs_model_specs=False` for
# the same reason as above: the refusal under test must be the one Rich's absence raises, on a machine
# where inference was never set up as much as on one where it was.
_RICH_MODE_BOOT_SCRIPT = _NO_RICH_PRELUDE + textwrap.dedent(
    """
    from pipelex.system.exceptions import MissingDependencyError

    try:
        Pipelex.make(
            integration_mode=INTEGRATION_MODE,
            needs_model_specs=False,
            config_overrides={"runtime": {"log": {"sink": "json", "pretty_print_mode": "rich"}}},
        )
    except MissingDependencyError as exc:
        print(f"refused: {exc.dependency_name} | {exc.extra_name} | {exc}")
    else:
        raise SystemExit("expected MissingDependencyError from a rich pretty-print mode without Rich")
    """
)


# `pipelex.test_extras.shared_pytest_plugins` loads in every session of every project that registers it, so a
# downstream suite installed without the extra must still collect and run. The blocker goes in at the top of
# the conftest, before the plugin is imported; `CI` is what puts the placeholder fixture on the path, which is
# where the console calls that used to break such a session were.
_DOWNSTREAM_CONFTEST = textwrap.dedent(
    """
    import importlib.abc
    import sys

    class _RichBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "rich" or fullname.startswith("rich."):
                raise ImportError(f"no-rich guard blocked '{fullname}'")
            return None

    sys.meta_path.insert(0, _RichBlocker())

    pytest_plugins = ["pipelex.test_extras.shared_pytest_plugins"]
    """
)

_DOWNSTREAM_TEST = textwrap.dedent(
    """
    def test_a_downstream_project_runs_its_own_test():
        assert True
    """
)


def _run_python(*, script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script, *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
        timeout=150,
    )


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> None:
    """Override the global module fixture: every boot here happens in a subprocess, so this process boots nothing."""


class TestRichFreeRun:
    @pytest.mark.parametrize("pretty_print_mode", [PrettyPrintMode.SILENT, PrettyPrintMode.POOR])
    def test_a_pipe_runs_with_rich_refused(self, pretty_print_mode: PrettyPrintMode) -> None:
        """The kernel boots and a direct-mode pipe runs with the json sink, a Rich-free pretty-print mode and no Rich importable."""
        result = _run_python(script=_RUN_SCRIPT, args=[pretty_print_mode.value])

        assert result.returncode == 0, f"rich-free run failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "rich-free run OK" in result.stdout
        stderr_lines = [line for line in result.stderr.splitlines() if line]
        match pretty_print_mode:
            case PrettyPrintMode.SILENT:
                # What a server writes: every stderr line is one JSON log record, and no ANSI anywhere.
                records = [json.loads(line) for line in stderr_lines]
                assert records, "expected the run's log records on stderr"
                assert all(isinstance(record, dict) and "severity" in record and "message" in record for record in records)
                assert "\x1b" not in result.stderr
            case PrettyPrintMode.POOR:
                # The poor printer frames the operator's output in plain text, its title's markup rendered away.
                assert any("Output of pipe greet → Text" in line for line in stderr_lines), result.stderr
                assert any("Hello world!" in line for line in stderr_lines), result.stderr
            case PrettyPrintMode.RICH:
                pytest.fail("the rich mode is the one this test refuses")

    def test_a_downstream_suite_registering_the_shared_plugin_runs_with_rich_refused(self, tmp_path: Path) -> None:
        """A project that registers the shared pytest plugin and installs no extra still collects and runs its tests."""
        (tmp_path / "conftest.py").write_text(_DOWNSTREAM_CONFTEST, encoding="utf-8")
        (tmp_path / "test_downstream.py").write_text(_DOWNSTREAM_TEST, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:randomly", "-q", "test_downstream.py"],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
            timeout=150,
            # `CI` is what the plugin reads to set the placeholder env vars, and disabling the entry-point
            # plugins keeps an unrelated third-party plugin's own Rich import out of the measurement.
            env={**os.environ, "CI": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        )

        assert result.returncode == 0, f"downstream suite failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        assert "1 passed" in result.stdout, result.stdout

    def test_the_rich_pretty_print_mode_is_refused_at_boot_naming_the_extra(self) -> None:
        """Without Rich, `pretty_print_mode = "rich"` stops the boot with the extra to install and the Rich-free modes."""
        result = _run_python(script=_RICH_MODE_BOOT_SCRIPT, args=[])

        assert result.returncode == 0, f"boot check failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        (refusal,) = [line for line in result.stdout.splitlines() if line.startswith("refused: ")]
        assert refusal.startswith(f"refused: rich | {RICH_EXTRA_NAME} | ")
        assert f"pipelex[{RICH_EXTRA_NAME}]" in refusal
        assert '"poor"' in refusal
        assert '"silent"' in refusal
