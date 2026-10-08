"""E2E: both CLIs run a published method on the hosted Pipelex API, by flag and by configured default.

Every case spawns the real `pipelex` or `pipelex-agent` binary against a live hosted API, so a run spends
hosted credits. That is why the `pipelex_api` marker keeps the module out of `make agent-test` and of the
default pytest selection, and why it is skipped when `PIPELEX_API_KEY` is unset. To run it against the dev
plane, export the key and the origin, then select the marker:

    export PIPELEX_API_KEY=<a dev-plane key>
    export PIPELEX_BASE_URL=https://api-dev.pipelex.com
    .venv/bin/pytest -m pipelex_api tests/e2e/pipelex/cli/test_hosted_run_cli.py

Without `PIPELEX_BASE_URL` the runs go to `https://api.pipelex.com`. The methods are the public
`github.com/Pipelex/methods` packages at a pinned tag, which the hosted API fetches itself.

Each test runs in its own `HOME` and `PIPELEX_HOME` (the hermetic-home fixture copies the kit's configuration
there), so nothing is read from or written to the developer's `~/.pipelex`. The subprocess environment is
built from nothing: it carries the Pipelex API key and base URL and no provider key, which is the point of a
hosted run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] — invokes the real pipelex binaries for E2E coverage
from pathlib import Path

import pytest

from pipelex.hosted.client_factory import HOSTED_API_DEFAULT_BASE_URL, PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELEX_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex"
PIPELEX_AGENT_BIN = REPO_ROOT / ".venv" / "bin" / "pipelex-agent"
SAMPLE_PDF = REPO_ROOT / "tests" / "data" / "documents" / "John-Doe-CV.pdf"

TEXT_STATS_REF = "github.com/Pipelex/methods/text_stats@v0.1.7"
DOCUMENTS_REF = "github.com/Pipelex/methods/documents@v0.1.7"
TEXT_INPUTS = '{"text": "Hello world. A second sentence follows."}'
#: An origin nothing listens on: a run that reached it would fail, so a run that succeeds went elsewhere.
UNREACHABLE_BASE_URL = "http://127.0.0.1:9"
#: Hosted runs poll until the run ends; an extraction takes a while on a cold plane.
RUN_TIMEOUT_SECONDS = 600.0

LOCAL_BUNDLE = """domain    = "hosted_e2e"
main_pipe = "shout"

[pipe.shout]
type        = "PipeLLM"
description = "Repeat a text in capitals"
inputs      = { text = "Text" }
output      = "Text"
prompt      = "Repeat $text in capitals."
"""

pytestmark = [
    pytest.mark.pipelex_api,
    pytest.mark.skipif(not os.environ.get(PIPELEX_API_KEY_ENV_KEY), reason=f"{PIPELEX_API_KEY_ENV_KEY} is not set"),
]


def _expected_base_url() -> str:
    return os.environ.get(PIPELEX_BASE_URL_ENV_KEY) or HOSTED_API_DEFAULT_BASE_URL


def _hosted_env(*, home: Path, base_url: str | None) -> dict[str, str]:
    """A subprocess environment holding the Pipelex API key and no provider key."""
    env = {
        "HOME": str(home),
        "PIPELEX_HOME": str(home / ".pipelex"),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        # Wide enough that Rich never wraps the lines the tests read.
        "COLUMNS": "250",
        PIPELEX_API_KEY_ENV_KEY: os.environ[PIPELEX_API_KEY_ENV_KEY],
    }
    if base_url is not None:
        env[PIPELEX_BASE_URL_ENV_KEY] = base_url
    return env


def _run(*, binary: Path, args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [str(binary), *args],
        env=env,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=RUN_TIMEOUT_SECONDS,
    )


def _set_run_execution(*, home: Path, execution: str) -> None:
    """Set `[run] execution` in the hermetic home's `pipelex.toml`, which the kit ships as `"local"`."""
    config_path = home / ".pipelex" / "pipelex.toml"
    original = config_path.read_text(encoding="utf-8")
    assert '\nexecution = "local"\n' in original, 'the kit\'s pipelex.toml no longer sets [run] execution = "local"'
    config_path.write_text(original.replace('\nexecution = "local"\n', f'\nexecution = "{execution}"\n'), encoding="utf-8")


def _single_output_dir(*, output_root: Path) -> Path:
    found = sorted(output_root.glob("*_output_*"))
    assert len(found) == 1, f"expected one run directory under {output_root}, found {found}"
    return found[0]


def _console(result: subprocess.CompletedProcess[str]) -> str:
    """What the human CLI printed: its final output goes to stdout, its banner, progress and recap to stderr."""
    return result.stdout + result.stderr


def _report(result: subprocess.CompletedProcess[str]) -> str:
    return f"exit {result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"


class TestHostedRunCli:
    def test_run_method_hosted_flag(self, hermetic_home: Path) -> None:
        """`pipelex run method <address> --hosted` runs on the hosted API and saves its outputs locally."""
        output_root = hermetic_home / "out"

        result = _run(
            binary=PIPELEX_BIN,
            args=["run", "method", TEXT_STATS_REF, "--hosted", "--inputs", TEXT_INPUTS, "-o", str(output_root)],
            env=_hosted_env(home=hermetic_home, base_url=os.environ.get(PIPELEX_BASE_URL_ENV_KEY)),
            cwd=hermetic_home,
        )

        assert result.returncode == 0, _report(result)
        assert f"Running on the hosted Pipelex API at {_expected_base_url()}" in _console(result)
        assert "Hosted run completed successfully" in _console(result)
        assert "Run id: run_" in _console(result)
        run_dir = _single_output_dir(output_root=output_root)
        assert run_dir.name == "text_stats_output_01"
        main_stuff = json.loads((run_dir / "main_stuff.json").read_text(encoding="utf-8"))
        assert "Sentences" in main_stuff["text"]
        assert (run_dir / "main_stuff.md").is_file()
        assert (run_dir / "working_memory.json").is_file()
        assert (run_dir / "graphspec.json").is_file()

    def test_configured_hosted_default_runs_without_a_flag(self, hermetic_home: Path) -> None:
        """`[run] execution = "hosted"` sends a run with no flag to the hosted API."""
        _set_run_execution(home=hermetic_home, execution="hosted")
        output_root = hermetic_home / "out"

        result = _run(
            binary=PIPELEX_BIN,
            args=["run", "method", TEXT_STATS_REF, "--inputs", TEXT_INPUTS, "-o", str(output_root)],
            env=_hosted_env(home=hermetic_home, base_url=os.environ.get(PIPELEX_BASE_URL_ENV_KEY)),
            cwd=hermetic_home,
        )

        assert result.returncode == 0, _report(result)
        assert f"Running on the hosted Pipelex API at {_expected_base_url()}" in _console(result)
        assert (_single_output_dir(output_root=output_root) / "main_stuff.json").is_file()

    def test_agent_run_method_runner_hosted(self, hermetic_home: Path) -> None:
        """`pipelex-agent run method <address> --runner hosted` answers the main output as JSON on stdout."""
        result = _run(
            binary=PIPELEX_AGENT_BIN,
            args=["run", "method", TEXT_STATS_REF, "--runner", "hosted", "--inputs", TEXT_INPUTS, "--format", "json"],
            env=_hosted_env(home=hermetic_home, base_url=os.environ.get(PIPELEX_BASE_URL_ENV_KEY)),
            cwd=hermetic_home,
        )

        assert result.returncode == 0, _report(result)
        main_stuff = json.loads(result.stdout)
        assert "Sentences" in main_stuff["text"]

    def test_base_url_flag_wins_over_the_environment(self, hermetic_home: Path) -> None:
        """`--base-url` wins over `PIPELEX_BASE_URL`, which here names an origin nothing listens on."""
        output_root = hermetic_home / "out"

        result = _run(
            binary=PIPELEX_BIN,
            args=[
                "run",
                "method",
                TEXT_STATS_REF,
                "--hosted",
                "--base-url",
                _expected_base_url(),
                "--inputs",
                TEXT_INPUTS,
                "-o",
                str(output_root),
            ],
            env=_hosted_env(home=hermetic_home, base_url=UNREACHABLE_BASE_URL),
            cwd=hermetic_home,
        )

        assert result.returncode == 0, _report(result)
        assert f"Running on the hosted Pipelex API at {_expected_base_url()}" in _console(result)
        assert UNREACHABLE_BASE_URL not in _console(result)

    def test_a_local_input_file_is_uploaded(self, hermetic_home: Path) -> None:
        """A relative path at a Document input, written in an inputs file, is uploaded and run as a storage URI."""
        inputs_dir = hermetic_home / "inputs"
        inputs_dir.mkdir()
        shutil.copy2(SAMPLE_PDF, inputs_dir / "cv.pdf")
        (inputs_dir / "inputs.json").write_text('{"document": "cv.pdf"}', encoding="utf-8")
        output_root = hermetic_home / "out"

        result = _run(
            binary=PIPELEX_BIN,
            args=[
                "run",
                "method",
                DOCUMENTS_REF,
                "--pipe",
                "extract_document_text",
                "--hosted",
                "--inputs",
                "inputs/inputs.json",
                "-o",
                str(output_root),
            ],
            env=_hosted_env(home=hermetic_home, base_url=os.environ.get(PIPELEX_BASE_URL_ENV_KEY)),
            cwd=hermetic_home,
        )

        assert result.returncode == 0, _report(result)
        assert "Uploaded 1 local file(s) for the run" in _console(result)
        run_dir = _single_output_dir(output_root=output_root)
        assert "pipelex-storage://" in (run_dir / "working_memory.json").read_text(encoding="utf-8")
        main_stuff = json.loads((run_dir / "main_stuff.json").read_text(encoding="utf-8"))
        assert "JOHN DOE" in main_stuff["text"].upper()

    def test_local_flag_overrides_a_hosted_default(self, hermetic_home: Path) -> None:
        """`--local` runs on this machine even when `[run] execution` is `"hosted"`.

        A live local run needs provider keys, which this module deliberately withholds, so the observable is a
        dry run instead: it needs no key, and it is a flag a hosted run refuses. The same command without
        `--local` is refused for asking a hosted run to dry-run, which proves the hosted default is in force and
        sends nothing; with `--local` it completes, which proves the run executed here.
        """
        _set_run_execution(home=hermetic_home, execution="hosted")
        bundle_path = hermetic_home / "bundle.mthds"
        bundle_path.write_text(LOCAL_BUNDLE, encoding="utf-8")
        output_root = hermetic_home / "out"
        dry_run_args = ["run", "bundle", str(bundle_path), "--dry-run", "--mock-inputs", "--no-graph", "-o", str(output_root)]
        env = _hosted_env(home=hermetic_home, base_url=os.environ.get(PIPELEX_BASE_URL_ENV_KEY))

        refused = _run(binary=PIPELEX_BIN, args=dry_run_args, env=env, cwd=hermetic_home)

        assert refused.returncode == 1, _report(refused)
        assert "only apply to a run on this machine" in _console(refused)

        local = _run(binary=PIPELEX_BIN, args=[*dry_run_args, "--local"], env=env, cwd=hermetic_home)

        assert local.returncode == 0, _report(local)
        assert "Dry run completed successfully" in _console(local)
        assert "Running on the hosted Pipelex API" not in _console(local)
        assert (_single_output_dir(output_root=output_root) / "working_memory.json").is_file()
