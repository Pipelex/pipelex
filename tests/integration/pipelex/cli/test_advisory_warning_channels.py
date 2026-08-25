"""Every whole-bundle validate channel carries the same advisory-warning families.

The `warnings` array used to be assembled site by site, and the sites disagreed: the protocol path
emitted the optionality and hint lints, the agent CLI, the builder ops and the bare CLI emitted the
optionality lint alone. One composition point (`pipelex.pipeline.advisory_warnings`) now builds them
all, and these pin that the channels agree — the agent-CLI JSON envelope, its markdown rendering,
the builder-ops envelopes, and the bare CLI's yellow echo.

`validate all` is the channel that reaches for the *library manager's* accumulated blueprints to
know which pipes are entry pipes (it holds no `ValidateBundleResult` of its own), so its case here
doubles as the proof that the `acquire_library` load path really does accumulate them.

One channel is deliberately absent: the builder's `validate_all`, which carries no `warnings` key
at all and never did — see `wip/full-optional/deferred.md`.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.builder.operations import validate_ops
from pipelex.cli.agent_cli.commands.validate._validate_core import validate_all_core, validate_bundle_core
from pipelex.cli.commands.validate._validate_core import (
    _validate_pipe_or_bundle,  # pyright: ignore[reportPrivateUsage]
    do_validate_all_libraries_and_dry_run,
)
from pipelex.pipeline.validation_render import format_validate_markdown
from pipelex.validation_error_types import HintLintErrorType, PipeValidationErrorType

if TYPE_CHECKING:
    from collections.abc import Iterator

_VACUOUS_MTHDS = """
domain = "advisory_channels"
description = "Bundle whose main pipe demands a structure that declares nothing"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }

[pipe.run]
type = "PipeLLM"
description = "Run with options"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"
"""

_ALL_FAMILIES_MTHDS = """
domain = "advisory_families"
description = "Bundle firing all three advisory families at once"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"
hints = { emphasis = "strong" }

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }

[pipe.run]
type = "PipeSequence"
description = "Force a guaranteed slot, then use it"
inputs = { opts = "RunOptions" }
output = "Text"
steps = [
  { pipe = "draft", result = "draft_text" },
  { pipe = "polish", result = "polished" },
]

[pipe.draft]
type = "PipeLLM"
description = "Draft from the options"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Draft with $opts"

[pipe.polish]
type = "PipeLLM"
description = "Polish a guaranteed draft"
inputs = { draft_text = "Text!" }
output = "Text"
prompt = "Polish $draft_text"
"""


def _write_bundle(*, contents: str, directory: Path) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(contents, encoding="utf-8")
    return bundle_path


@pytest.fixture
def vacuous_bundle_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        _write_bundle(contents=_VACUOUS_MTHDS, directory=directory)
        yield directory


@pytest.fixture
def all_families_bundle_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        _write_bundle(contents=_ALL_FAMILIES_MTHDS, directory=directory)
        yield directory


def _error_types(warnings: list[dict[str, Any]]) -> list[str]:
    return [warning["error_type"] for warning in warnings]


class TestAdvisoryWarningChannels:
    # ---- `validate all`: entry pipes read off the library manager's accumulated blueprints ----

    def test_agent_cli_validate_all_warns_on_the_main_pipe(self, vacuous_bundle_dir: Path) -> None:
        result = asyncio.run(validate_all_core(library_dirs=[vacuous_bundle_dir]))

        assert result["is_valid"] is True
        vacuous = [warning for warning in result["warnings"] if warning["error_type"] == PipeValidationErrorType.INPUT_PRESENCE_VACUOUS]
        assert len(vacuous) == 1
        assert vacuous[0]["pipe_code"] == "run"
        assert vacuous[0]["domain_code"] == "advisory_channels"
        assert vacuous[0]["variable_names"] == ["opts"]

    # ---- `validate bundle`: entry pipes read off the batch's blueprints -----------------------

    def test_agent_cli_validate_bundle_envelope(self, vacuous_bundle_dir: Path) -> None:
        result = asyncio.run(validate_bundle_core(bundle_path=vacuous_bundle_dir / "bundle.mthds", library_dirs=[vacuous_bundle_dir]))

        assert result["is_valid"] is True
        assert result["is_runnable"] is True
        vacuous = [warning for warning in result["warnings"] if warning["error_type"] == PipeValidationErrorType.INPUT_PRESENCE_VACUOUS]
        assert len(vacuous) == 1
        assert "declares no required field" in vacuous[0]["message"]
        # The locator is the pipe, never the concept: `concept_code` on a pipe_validation item is
        # reserved for a reference that did not resolve, spelled as the author wrote it.
        assert "concept_code" not in vacuous[0]

    def test_builder_validate_bundle_content_twin(self) -> None:
        result = asyncio.run(validate_ops.validate_bundle_content(mthds_contents=[_VACUOUS_MTHDS]))

        assert result["is_valid"] is True
        assert PipeValidationErrorType.INPUT_PRESENCE_VACUOUS in _error_types(result["warnings"])

    def test_agent_cli_markdown_renders_the_warning_under_its_heading(self, vacuous_bundle_dir: Path) -> None:
        """The markdown stream is the one an agent actually reads on `--format markdown` (the default)."""
        result = asyncio.run(validate_bundle_core(bundle_path=vacuous_bundle_dir / "bundle.mthds", library_dirs=[vacuous_bundle_dir]))

        markdown = format_validate_markdown(result)
        assert "# Validation passed" in markdown
        assert "## Warnings" in markdown
        assert f"- **{PipeValidationErrorType.INPUT_PRESENCE_VACUOUS}** — Input 'opts' of pipe 'advisory_channels.run'" in markdown

    # ---- All three families, one bundle, one fixed order, every channel ----------------------

    def test_agent_cli_bundle_envelope_carries_all_three_families(self, all_families_bundle_dir: Path) -> None:
        result = asyncio.run(validate_bundle_core(bundle_path=all_families_bundle_dir / "bundle.mthds", library_dirs=[all_families_bundle_dir]))

        assert _error_types(result["warnings"]) == [
            PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT,
            PipeValidationErrorType.INPUT_PRESENCE_VACUOUS,
            HintLintErrorType.HINT_UNKNOWN_KEY,
        ]

    def test_builder_bundle_file_envelope_carries_all_three_families(self, all_families_bundle_dir: Path) -> None:
        result = asyncio.run(
            validate_ops.validate_bundle_file(bundle_path=all_families_bundle_dir / "bundle.mthds", library_dirs=[all_families_bundle_dir])
        )

        assert _error_types(result["warnings"]) == [
            PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT,
            PipeValidationErrorType.INPUT_PRESENCE_VACUOUS,
            HintLintErrorType.HINT_UNKNOWN_KEY,
        ]

    def test_agent_cli_markdown_lists_all_three_families_in_the_same_order(self, all_families_bundle_dir: Path) -> None:
        result = asyncio.run(validate_bundle_core(bundle_path=all_families_bundle_dir / "bundle.mthds", library_dirs=[all_families_bundle_dir]))

        markdown = format_validate_markdown(result)
        assert "## Warnings (3)" in markdown
        rendered = [line for line in markdown.splitlines() if line.startswith("- **")]
        assert [line.split("**")[1] for line in rendered] == [
            PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT,
            PipeValidationErrorType.INPUT_PRESENCE_VACUOUS,
            HintLintErrorType.HINT_UNKNOWN_KEY,
        ]

    def test_bare_cli_bundle_echo_carries_all_three_families(self, all_families_bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """The bare CLI's yellow echo is the third presentation surface, and the one that used to
        carry the optionality lint alone.
        """
        asyncio.run(_validate_pipe_or_bundle(bundle_path=all_families_bundle_dir / "bundle.mthds", library_dirs=[all_families_bundle_dir]))

        echoed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Warning: ")]
        assert len(echoed) == 3
        assert "is declared with a force marker ('!')" in echoed[0]
        assert "declares no required field" in echoed[1]
        assert "is not defined by this version of the standard" in echoed[2]

    def test_bare_cli_validate_all_echo_carries_the_entry_pipe_lint(self, vacuous_bundle_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        do_validate_all_libraries_and_dry_run(library_dirs=[vacuous_bundle_dir])

        echoed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Warning: ")]
        assert len(echoed) == 1
        assert "Input 'opts' of pipe 'advisory_channels.run'" in echoed[0]
