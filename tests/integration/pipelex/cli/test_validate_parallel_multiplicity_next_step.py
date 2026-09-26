"""Pin: a `PipeParallel` whose branch and field differ in multiplicity is refused with its next step.

The combine of the branch results is the existing check, reached in the dry run of validate; it stays as
it is. What these tests pin is what the refusal carries: the branch, the result, the field and which of
the two multiplicities to change, on ``pipelex validate bundle`` and in ``pipelex-agent validate bundle``'s
JSON, and a top-level next step that sends the reader to the items instead of to "the array".
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
import typer
from rich.console import Console

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd as agent_validate_bundle_cmd
from pipelex.cli.commands.validate._validate_core import _validate_pipe_or_bundle  # pyright: ignore[reportPrivateUsage]
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

# A list branch fed into a single field: `draft_ideas` gives `Idea[]` for the result `ideas`, while the
# field `ideas` of `TopicReview` holds one `Idea`. Every pipe is a PipeCompose or a controller.
_LIST_BRANCH_INTO_SINGLE_FIELD = """
domain      = "brainstorm"
description = "A parallel feeding a list branch into a single field"
main_pipe   = "analyze_topics"

[concept.Topic]
description = "A topic to explore"
refines     = "Text"

[concept.Idea]
description = "One idea about a topic"
refines     = "Text"

[concept.Overview]
description = "A one-line overview"
refines     = "Text"

[concept.TopicReview]
description = "Ideas and an overview"

[concept.TopicReview.structure]
ideas    = { type = "concept", concept_ref = "Idea", description = "The ideas", required = true }
overview = { type = "concept", concept_ref = "Overview", description = "The overview", required = true }

[pipe.analyze_topics]
type        = "PipeParallel"
description = "Draft the ideas and the overview at the same time"
inputs      = { topics = "Topic[]" }
output      = "TopicReview"
branches    = [
  { pipe = "draft_ideas", result = "ideas" },
  { pipe = "write_overview", result = "overview" },
]

[pipe.draft_ideas]
type             = "PipeBatch"
description      = "Draft one idea per topic"
inputs           = { topics = "Topic[]" }
output           = "Idea[]"
branch_pipe_code = "draft_idea"
input_list_name  = "topics"
input_item_name  = "topic"

[pipe.draft_idea]
type        = "PipeCompose"
description = "Draft one idea about a topic"
inputs      = { topic = "Topic" }
output      = "Idea"
template    = "An idea worth exploring about $topic"

[pipe.write_overview]
type        = "PipeCompose"
description = "Write a one-line overview"
output      = "Overview"
template    = "One idea per topic."
"""

# The reverse: `draft_idea` gives one `Idea` for the result `ideas`, while the field holds a list.
_SINGLE_BRANCH_INTO_LIST_FIELD = """
domain      = "brainstorm"
description = "A parallel feeding a single branch into a list field"
main_pipe   = "analyze_topic"

[concept.Idea]
description = "One idea about a topic"
refines     = "Text"

[concept.Overview]
description = "A one-line overview"
refines     = "Text"

[concept.TopicReview]
description = "Ideas and an overview"

[concept.TopicReview.structure]
ideas    = { type = "list", item_type = "concept", item_concept_ref = "Idea", description = "The ideas", required = true }
overview = { type = "concept", concept_ref = "Overview", description = "The overview", required = true }

[pipe.analyze_topic]
type        = "PipeParallel"
description = "Draft the idea and the overview at the same time"
inputs      = { topic = "Text" }
output      = "TopicReview"
branches    = [
  { pipe = "draft_idea", result = "ideas" },
  { pipe = "write_overview", result = "overview" },
]

[pipe.draft_idea]
type        = "PipeCompose"
description = "Draft one idea about the topic"
inputs      = { topic = "Text" }
output      = "Idea"
template    = "An idea worth exploring about $topic"

[pipe.write_overview]
type        = "PipeCompose"
description = "Write a one-line overview"
output      = "Overview"
template    = "One idea."
"""

# The list comes from the branch itself: `draft_idea` declares one `Idea`, but the branch batches it over
# the topics, so the next step names that branch setting rather than the pipe's declared output.
_BATCHED_BRANCH_INTO_SINGLE_FIELD = _LIST_BRANCH_INTO_SINGLE_FIELD.replace(
    '{ pipe = "draft_ideas", result = "ideas" }',
    '{ pipe = "draft_idea", result = "ideas", batch_over = "topics", batch_as = "topic" }',
)

_BATCHED_INTO_SINGLE_NEXT_STEP = (
    "Branch 'draft_idea' gives result 'ideas' as a list, 'Idea[]', but field 'ideas' of 'TopicReview' holds a single item. "
    "Declare the field as a list in the structure of 'TopicReview', with type 'list', item_type 'concept' and item_concept_ref 'Idea', "
    "or change the nb_output, multiple_output or batch_over that branch 'draft_idea' sets in the parallel's branches."
)

# Two faults in one combine: the ideas are a multiplicity mismatch, while the overview field receives a
# list of `Idea`, a concept that does not fit `Overview` whatever its multiplicity. Only the first gets a
# multiplicity next step, and the combine's own report is kept for the second.
_TWO_FAULTS_IN_ONE_COMBINE = _LIST_BRANCH_INTO_SINGLE_FIELD.replace(
    '{ pipe = "write_overview", result = "overview" }',
    '{ pipe = "draft_ideas", result = "overview" }',
)

_LIST_INTO_SINGLE_NEXT_STEP = (
    "Branch 'draft_ideas' gives result 'ideas' as a list, 'Idea[]', but field 'ideas' of 'TopicReview' holds a single item. "
    "Declare the field as a list in the structure of 'TopicReview', with type 'list', item_type 'concept' and item_concept_ref 'Idea', "
    "or make branch 'draft_ideas' output a single 'Idea'."
)

_SINGLE_INTO_LIST_NEXT_STEP = (
    "Branch 'draft_idea' gives result 'ideas' as a single 'Idea', but field 'ideas' of 'TopicReview' holds a list. "
    "Declare the field as a single concept in the structure of 'TopicReview', with type 'concept' and concept_ref 'Idea', "
    "or make branch 'draft_idea' output 'Idea[]'."
)

_TOP_LEVEL_NEXT_STEP = "Edit the bundle as each validation error says"


def _write_bundle(*, directory: Path, content: str) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
    return bundle_path


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    """A recording console patched into the error handlers, so the panel can be read back."""
    recorded_console = Console(width=400, record=True, color_system=None)
    mocker.patch("pipelex.cli.error_handlers.get_console", return_value=recorded_console)
    return recorded_console


class TestValidateParallelMultiplicityNextStep:
    @pytest.mark.parametrize(
        ("bundle_content", "expected_next_step"),
        [
            (_LIST_BRANCH_INTO_SINGLE_FIELD, _LIST_INTO_SINGLE_NEXT_STEP),
            (_SINGLE_BRANCH_INTO_LIST_FIELD, _SINGLE_INTO_LIST_NEXT_STEP),
            (_BATCHED_BRANCH_INTO_SINGLE_FIELD, _BATCHED_INTO_SINGLE_NEXT_STEP),
        ],
        ids=["list_branch_into_single_field", "single_branch_into_list_field", "batched_branch_into_single_field"],
    )
    def test_bare_validate_bundle_names_the_multiplicity_to_change(
        self, console: Console, tmp_path: Path, bundle_content: str, expected_next_step: str
    ) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=bundle_content)

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_validate_pipe_or_bundle(bundle_path=bundle_path, library_dirs=[bundle_path.parent]))

        assert exc_info.value.exit_code == 1
        # The console wraps long lines; the words, not the line breaks, are what the reader gets.
        output = " ".join(console.export_text().split())
        assert "Bundle validation failed" in output
        assert expected_next_step in output
        assert f"💡 Tip: {_TOP_LEVEL_NEXT_STEP}" in output
        assert "Check the validation_errors array" not in output
        assert "Traceback" not in output

    def test_a_concept_mismatch_keeps_the_combine_report(self, tmp_path: Path) -> None:
        """A branch whose concept does not fit its field gets no multiplicity advice, and its refusal is not hidden."""
        bundle_path = _write_bundle(directory=tmp_path, content=_TWO_FAULTS_IN_ONE_COMBINE)

        with pytest.raises(ValidateBundleError) as raised:
            asyncio.run(validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent]))

        (item,) = raised.value.to_error_report().validation_errors or []
        assert _LIST_INTO_SINGLE_NEXT_STEP in item.message
        assert "gives result 'overview'" not in item.message
        assert "The combine also reported: Error combining stuffs for concept TopicReview" in item.message

    def test_agent_validate_bundle_json_carries_the_next_step(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_LIST_BRANCH_INTO_SINGLE_FIELD)
        mocker.patch("pipelex.cli.agent_cli.commands.validate.bundle_cmd.make_pipelex_for_agent_cli")
        mocker.patch("pipelex.cli.agent_cli.commands.validate.bundle_cmd.Pipelex.teardown_if_needed")
        try:
            with pytest.raises(typer.Exit) as exc_info:
                agent_validate_bundle_cmd(
                    path=str(bundle_path),
                    library_dir=[str(bundle_path.parent)],
                    output_format=CliOutputFormat.JSON,
                )
        finally:
            set_agent_cli_error_format(CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["is_valid"] is False
        assert envelope["error_domain"] == "input"
        assert envelope["hint"].startswith(_TOP_LEVEL_NEXT_STEP)
        (item,) = envelope["validation_errors"]
        assert item["category"] == "dry_run"
        assert "PipeParallel 'analyze_topics' cannot combine its branch results into its output 'TopicReview'." in item["message"]
        assert _LIST_INTO_SINGLE_NEXT_STEP in item["message"]

    def test_the_verdict_report_carries_both_next_steps(self, tmp_path: Path) -> None:
        """The report every surface draws from: the item names the fix, the top level points at the items."""
        bundle_path = _write_bundle(directory=tmp_path, content=_LIST_BRANCH_INTO_SINGLE_FIELD)

        with pytest.raises(ValidateBundleError) as raised:
            asyncio.run(validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent]))

        report = raised.value.to_error_report()
        assert (report.user_action_detail() or "").startswith(_TOP_LEVEL_NEXT_STEP)
        (item,) = report.validation_errors or []
        assert _LIST_INTO_SINGLE_NEXT_STEP in item.message
