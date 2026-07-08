"""Integration tests for ``pipelex-agent fix bundle`` command logic."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
import tomlkit
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from typing import Any

    from pytest_mock import MockerFixture

FIX_BUNDLE_MODULE = "pipelex.cli.agent_cli.commands.fix.bundle_cmd"

_FIXABLE_SEQUENCE_MTHDS = """domain = "agent_fix_bundle"
main_pipe = "list_ideas"

[concept]
Idea = "An idea."

[pipe.gen_ideas]
type = "PipeLLM"
description = "Generate ideas."
inputs = { topic = "Text" }
output = "Idea[]"
prompt = "Generate ideas about $topic"

[pipe.list_ideas]
type = "PipeSequence"
description = "Sequence declaring a single output while the last step yields a list."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_ideas", result = "ideas" },
]
"""

_UNFIXABLE_MTHDS = """domain = "agent_fix_unfixable"
main_pipe = "say_hi"

[pipe.say_hi]
type = "PipeLLM"
description = "References a missing concept."
inputs = { name = "MissingConcept" }
output = "Text"
prompt = "Say hi to $name"
"""

_SIGNATURE_ONLY_MTHDS = """domain = "agent_fix_signature"
main_pipe = "summarize_doc"

[concept]
SigDocument = "A document concept used for testing signatures."

[pipe.summarize_doc]
description = "Produces a summary of a document (contract only)."
inputs = { doc = "SigDocument" }
output = "Text"
"""


def _pipes(bundle_path: Path) -> dict[str, Any]:
    parsed = tomlkit.loads(bundle_path.read_text(encoding="utf-8")).unwrap()
    return cast("dict[str, Any]", parsed["pipe"])


def _patch_setup(mocker: MockerFixture) -> None:
    mocker.patch(f"{FIX_BUNDLE_MODULE}.make_pipelex_for_agent_cli")
    mocker.patch(f"{FIX_BUNDLE_MODULE}.Pipelex.teardown_if_needed")


class TestAgentFixBundle:
    def test_fixable_bundle_exits_zero_and_mutates_file(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        _patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["is_valid"] is True
        assert [fix["fix_code"] for fix in payload["fixes_applied"]] == ["match-sequence-output"]
        assert payload["files_written"] == [str(bundle_path.resolve())]
        assert _pipes(bundle_path)["list_ideas"]["output"] == "Idea[]"

    def test_unfixable_bundle_exits_one_with_structured_error(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        _patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_UNFIXABLE_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        payload = json.loads(capsys.readouterr().err)
        assert payload["error_type"] == "FixBundleError"
        assert payload["is_valid"] is False
        assert payload["fixes_applied"] == []
        assert payload["remaining_errors"]

    def test_signature_only_bundle_exits_one_after_success_payload(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        _patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_SIGNATURE_ONLY_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(path=str(bundle_path), output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert captured.err == ""
        payload = json.loads(captured.out)
        assert payload["success"] is True
        assert payload["is_valid"] is True
        assert payload["is_runnable"] is False
        assert payload["pending_signatures"] == ["agent_fix_signature.summarize_doc"]
        assert payload["fixes_applied"] == []
        assert payload["remaining_errors"] == []

    def test_select_filter_is_honored_end_to_end(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        _patch_setup(mocker)
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_FIXABLE_SEQUENCE_MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exc_info:
            fix_bundle_cmd(
                path=str(bundle_path),
                select_codes_raw=["strip-namespace"],
                output_format=CliOutputFormat.JSON,
            )

        assert exc_info.value.exit_code == 1
        payload = json.loads(capsys.readouterr().err)
        assert payload["is_valid"] is False
        assert payload["fixes_applied"] == []
        assert _pipes(bundle_path)["list_ideas"]["output"] == "Idea"
