"""E2E test that the agent CLI's stdout stays clean for JSON-emitting commands.

Downstream tooling (e.g. ``mthds-js``'s ``PipelexMTHDSProtocol``) calls ``JSON.parse(stdout)``
on commands like ``pipelex-agent models --format json``. The package-default
``console_log_target`` / ``console_print_target`` must therefore route logs and rich
prints to stderr — otherwise a single log line on a setup code path will break every
downstream consumer.

This test spawns a real ``pipelex-agent`` subprocess with an isolated ``HOME`` (so no
user-local ``~/.pipelex/`` overrides leak in). The hermetic ``~/.pipelex/pipelex.toml``
is rewritten to set ``package_log_levels.pipelex = "DEBUG"`` so existing setup-time
``log.debug(...)`` calls (e.g. ``telemetry_factory.py``) actually fire — that's the same
flip any user can make in their override file, and it's the scenario described in PR
#452's intent ("default to stderr for outputs happening before initialization").

With ``console_log_target = "stdout"`` (the bug), those DEBUG lines land on stdout and
break ``json.loads``. With ``console_log_target = "stderr"`` (the fix), they land on
stderr and stdout stays clean.

Asserts that:

  - the command exits 0
  - the captured stdout parses as JSON in one shot via ``json.loads`` — no stripping,
    no last-object hunting.

If anyone flips the kit-template / package default back to stdout, or adds a
``print(...)`` on the models command path that targets stdout, this test fails.
"""

from __future__ import annotations

import json
import subprocess  # noqa: S404 — invokes the real pipelex-agent binary for E2E coverage
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path
from tests.e2e.agent_cli.conftest import PIPELEX_AGENT_BIN

if TYPE_CHECKING:
    from pathlib import Path


def _set_package_log_level(pipelex_toml_path: Path, *, package_name: str, level: str) -> None:
    """Set ``<package_name> = "<level>"`` inside ``[pipelex.log_config.package_log_levels]``.

    Uses the project's ``tomlkit``-based helpers (the same pair ``init_cmd`` relies
    on) to parse-edit-dump the file. This handles every edge case the previous
    line-based rewriter had to special-case (duplicate section headers, whitespace
    variants in key lines, missing trailing newlines) — tomlkit's parser is the
    source of truth for what the agent CLI ultimately reads back via Pipelex's
    config loader.
    """
    doc = load_toml_with_tomlkit(pipelex_toml_path)
    doc["pipelex"]["log_config"]["package_log_levels"][package_name] = level  # type: ignore[index]
    save_toml_to_path(doc, pipelex_toml_path)


def _set_pipelex_package_log_level_to_debug(pipelex_toml_path: Path) -> None:
    """Compatibility shim for the original two callers — bumps pipelex to DEBUG."""
    _set_package_log_level(pipelex_toml_path, package_name="pipelex", level="DEBUG")


def _assert_stderr_is_clean_or_structured_envelope(stderr: str) -> None:
    """Assert that ``stderr`` is either empty or a parseable structured error envelope.

    The agent CLI's contract is: stderr is reserved for the structured error envelope
    (a JSON object with an ``error`` field). The strictest catch on a third-party
    logger leak is: any free-floating log line on stderr would NOT be valid JSON, so
    ``json.loads`` fails. This relaxation lets the test tolerate the edge case where
    the envelope itself legitimately appears on stderr (which would never happen on a
    successful run, but it absorbs unrelated environmental noise that still parses
    cleanly), while still failing loudly on the log-leak shape we actually guard
    against.
    """
    if stderr == "":
        return
    try:
        parsed = json.loads(stderr)
    except json.JSONDecodeError as exc:
        msg = (
            f"stderr must be either empty or a parseable JSON error envelope — any other "
            f"content (log line, warning, print) means something leaked through the agent "
            f"CLI's stdout/stderr discipline.\nstderr={stderr!r}\nparse error={exc!s}"
        )
        raise AssertionError(msg) from exc
    if not (isinstance(parsed, dict) and "error" in parsed):
        msg = (
            f"stderr parsed as JSON but is not the structured error envelope shape (expected a dict containing an ``error`` key).\nstderr={stderr!r}"
        )
        raise AssertionError(msg)


def _set_console_targets(pipelex_toml_path: Path, *, log_target: str, print_target: str) -> None:
    """Rewrite ``console_log_target`` and ``console_print_target`` directly under
    ``[pipelex.log_config]`` to the given values.

    Used by the adversarial defense-in-depth test to simulate a user who overrides both
    targets to ``"stdout"`` in their ``~/.pipelex/pipelex.toml``. The agent CLI must keep
    its stdout channel clean for JSON consumers regardless of this user config.

    Asserts on no-match for either knob so a future kit refactor surfaces here instead of
    silently neutering the test.
    """
    original_text = pipelex_toml_path.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)
    in_target_section = False
    log_target_rewritten = False
    print_target_rewritten = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_target_section = stripped == "[pipelex.log_config]"
            continue
        if not in_target_section:
            continue
        if stripped.startswith("console_log_target"):
            lines[index] = f'console_log_target = "{log_target}"\n'
            log_target_rewritten = True
        elif stripped.startswith("console_print_target"):
            lines[index] = f'console_print_target = "{print_target}"\n'
            print_target_rewritten = True
    if not log_target_rewritten:
        msg = f"Could not find 'console_log_target = ...' under [pipelex.log_config] in {pipelex_toml_path}"
        raise AssertionError(msg)
    if not print_target_rewritten:
        msg = f"Could not find 'console_print_target = ...' under [pipelex.log_config] in {pipelex_toml_path}"
        raise AssertionError(msg)
    pipelex_toml_path.write_text("".join(lines), encoding="utf-8")


@pytest.mark.gha_disabled  # Slow subprocess-based E2E; runs locally and on PR-gated workflows.
class TestAgentCliStdoutIsCleanJson:
    def test_models_json_stdout_parses_as_single_json_document(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """``pipelex-agent models --format json`` stdout must be a single JSON document.

        Bumps ``package_log_levels.pipelex`` to DEBUG (the exact knob a downstream user
        would flip when debugging) so the latent ``console_log_target`` bug surfaces as
        DEBUG lines on stdout. The agent CLI's ``config_overrides`` MUST win over the
        user-TOML override (pinning pipelex to OFF), so ``json.loads`` on the entire
        stdout must succeed and return a dict envelope.
        """
        _set_pipelex_package_log_level_to_debug(hermetic_home / ".pipelex" / "pipelex.toml")

        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_AGENT_BIN),
                "models",
                "--format",
                "json",
            ],
            env=offline_subprocess_env,
            cwd=str(hermetic_home),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode == 0, f"pipelex-agent models --format json must succeed.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            msg = (
                f"stdout must be a single parseable JSON document (no log/print pollution).\n"
                f"stdout={result.stdout!r}\nstderr={result.stderr!r}\nparse error={exc!s}"
            )
            raise AssertionError(msg) from exc

        assert isinstance(parsed, dict), f"Expected a JSON object envelope; got {type(parsed).__name__}: {parsed!r}"
        payload = cast("dict[str, object]", parsed)
        assert payload.get("success") is True, f"Expected ``success=True`` in envelope; got {payload!r}"

    def test_models_json_stdout_and_stderr_stay_clean_under_third_party_logger_enabled(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Regression for the third-party-logger leak: even when the user bumps a
        third-party logger (anthropic, httpx) to DEBUG in their ``pipelex.toml``, the
        agent CLI's stdout AND stderr channels must stay clean — stdout parseable as a
        single JSON envelope, stderr free of any log line that would corrupt the
        structured error envelope.

        Before the fix the agent CLI's ``package_log_levels`` override only pinned
        ``pipelex = OFF`` and let third-party loggers keep their configured level,
        leaking INFO/DEBUG records onto stderr via the root's RichHandler. The fix is
        ``logging.disable(sys.maxsize)`` at the start of every agent CLI entry point
        — a process-global cutoff that blocks every record for every logger at every
        level (including custom levels above CRITICAL), regardless of which package
        emits.
        """
        pipelex_toml = hermetic_home / ".pipelex" / "pipelex.toml"
        for package_name in ("anthropic", "httpx", "botocore", "openai"):
            _set_package_log_level(pipelex_toml, package_name=package_name, level="DEBUG")

        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_AGENT_BIN),
                "models",
                "--format",
                "json",
            ],
            env=offline_subprocess_env,
            cwd=str(hermetic_home),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode == 0, (
            f"pipelex-agent models --format json must succeed with third-party loggers at DEBUG.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        # stdout must parse as JSON in one shot — no log line preceding/following the envelope.
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, dict)
        # stderr must be either empty (the expected case for a successful run) or a
        # parseable structured error envelope — anything else (log line, warning, print)
        # proves a third-party logger leaked through the root RichHandler.
        _assert_stderr_is_clean_or_structured_envelope(result.stderr)

    def test_models_json_stdout_resists_user_targets_override_to_stdout(
        self,
        hermetic_home: Path,
        offline_subprocess_env: dict[str, str],
    ) -> None:
        """Adversarial defense-in-depth: even when the user's ``pipelex.toml`` sets BOTH
        ``console_log_target = "stdout"`` and ``console_print_target = "stdout"`` AND
        bumps ``package_log_levels.pipelex`` to DEBUG, the agent CLI's stdout channel
        must remain a clean, parseable JSON envelope.

        The agent CLI's stdout-as-JSON contract is too important to leave at the mercy of
        the user's ``~/.pipelex/pipelex.toml``. ``make_pipelex_for_agent_cli`` injects
        config_overrides that pin both targets to stderr from the very first log/print
        call during ``Pipelex.make()`` — so this test exercises the override defense end
        to end, not just the shipped TOML defaults.
        """
        pipelex_toml = hermetic_home / ".pipelex" / "pipelex.toml"
        _set_pipelex_package_log_level_to_debug(pipelex_toml)
        _set_console_targets(pipelex_toml, log_target="stdout", print_target="stdout")

        result = subprocess.run(  # noqa: S603
            [
                str(PIPELEX_AGENT_BIN),
                "models",
                "--format",
                "json",
            ],
            env=offline_subprocess_env,
            cwd=str(hermetic_home),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert result.returncode == 0, (
            f"pipelex-agent models --format json must succeed under adversarial user override.\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            msg = (
                f"stdout must stay parseable JSON even when the user pipelex.toml routes "
                f"both console_log_target and console_print_target to stdout — the agent CLI "
                f"factory must override them back to stderr.\n"
                f"stdout={result.stdout!r}\nstderr={result.stderr!r}\nparse error={exc!s}"
            )
            raise AssertionError(msg) from exc

        assert isinstance(parsed, dict), f"Expected a JSON object envelope; got {type(parsed).__name__}: {parsed!r}"
        payload = cast("dict[str, object]", parsed)
        assert payload.get("success") is True, f"Expected ``success=True`` in envelope; got {payload!r}"
