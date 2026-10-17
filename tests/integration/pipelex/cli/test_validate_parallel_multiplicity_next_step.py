"""Pin: a `PipeParallel` whose branch and field differ in multiplicity is refused as the method's fault, located at the parallel.

The combine of the branch results is the existing check, reached in the dry run of validate; it stays as
it is. What these tests pin is what the verdict carries for the caller: one item coded
``pipe.output_multiplicity``, rendered from the result, the declared and the produced multiplicities, on
``pipelex validate bundle`` and in ``pipelex-agent validate bundle``'s JSON, and a top-level next step that
sends the reader to the items instead of to "the array". The combine's own restatement, which names the
branch to change, is the operator's: no caller reads it.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode, StepKind
from rich.console import Console

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.validate.bundle_cmd import validate_bundle_cmd as agent_validate_bundle_cmd
from pipelex.cli.commands.validate._validate_core import _validate_pipe_or_bundle  # pyright: ignore[reportPrivateUsage]
from pipelex.errors.problem import PipelexProblem, ProblemView
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
# the topics, so the parallel receives a list for its single field all the same.
_BATCHED_BRANCH_INTO_SINGLE_FIELD = _LIST_BRANCH_INTO_SINGLE_FIELD.replace(
    '{ pipe = "draft_ideas", result = "ideas" }',
    '{ pipe = "draft_idea", result = "ideas", batch_over = "topics", batch_as = "topic" }',
)

# Two faults in one combine: the ideas are a multiplicity mismatch, while the overview field receives a
# list of `Idea`, a concept that does not fit `Overview` whatever its multiplicity. Only the first is a
# multiplicity fault, which the verdict's item reports.
_TWO_FAULTS_IN_ONE_COMBINE = _LIST_BRANCH_INTO_SINGLE_FIELD.replace(
    '{ pipe = "write_overview", result = "overview" }',
    '{ pipe = "draft_ideas", result = "overview" }',
)

# No advice where a multiplicity change would not make the branch fit: a single `Text` into a list of
# plain strings, whose items are not concept contents, and an `Anything[]` branch, whose concept has no
# structure class to compare. The verdict's item reports an output that does not fit its concept instead.
_TEXT_INTO_PRIMITIVE_LIST_FIELD = _SINGLE_BRANCH_INTO_LIST_FIELD.replace(
    'ideas    = { type = "list", item_type = "concept", item_concept_ref = "Idea", description = "The ideas", required = true }',
    'ideas    = { type = "list", item_type = "text", description = "The ideas", required = true }',
)

_ANYTHING_LIST_INTO_SINGLE_FIELD = _LIST_BRANCH_INTO_SINGLE_FIELD.replace('output           = "Idea[]"', 'output           = "Anything[]"')

_LIST_INTO_SINGLE_SENTENCE = "Pipe 'analyze_topics' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'."

_SINGLE_INTO_LIST_SENTENCE = "Pipe 'analyze_topic' produced an output of the multiplicity 'single', but its output 'ideas' is declared 'list'."

_TOP_LEVEL_NEXT_STEP = "Edit the bundle as each validation error says"


def _write_bundle(*, directory: Path, content: str) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
    return bundle_path


@pytest.fixture
def console(mocker: MockerFixture) -> Console:
    """A recording console patched into the error handlers, so the panel can be read back."""
    recorded_console = Console(width=400, record=True, color_system=None)
    mocker.patch("pipelex.cli.error_handlers.get_error_console", return_value=recorded_console)
    return recorded_console


def _verdict_problem(*, bundle_path: Path) -> PipelexProblem:
    """The caller's view of the invalid verdict validate gives the bundle."""
    with pytest.raises(ValidateBundleError) as raised:
        asyncio.run(validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent]))
    return raised.value.to_problem(view=ProblemView.CALLER)


class TestValidateParallelMultiplicityNextStep:
    @pytest.mark.parametrize(
        ("bundle_content", "expected_item"),
        [
            (_LIST_BRANCH_INTO_SINGLE_FIELD, f"Pipe 'analyze_topics' failed its dry run: {_LIST_INTO_SINGLE_SENTENCE}"),
            (_SINGLE_BRANCH_INTO_LIST_FIELD, f"Pipe 'analyze_topic' failed its dry run: {_SINGLE_INTO_LIST_SENTENCE}"),
            (_BATCHED_BRANCH_INTO_SINGLE_FIELD, f"Pipe 'analyze_topics' failed its dry run: {_LIST_INTO_SINGLE_SENTENCE}"),
        ],
        ids=["list_branch_into_single_field", "single_branch_into_list_field", "batched_branch_into_single_field"],
    )
    def test_bare_validate_bundle_names_the_multiplicity_to_change(
        self, console: Console, tmp_path: Path, bundle_content: str, expected_item: str
    ) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=bundle_content)

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(_validate_pipe_or_bundle(bundle_path=bundle_path, library_dirs=[bundle_path.parent]))

        assert exc_info.value.exit_code == 1
        # The console wraps long lines; the words, not the line breaks, are what the reader gets.
        output = " ".join(console.export_text().split())
        assert "Bundle validation failed" in output
        assert expected_item in output
        assert f"💡 Tip: {_TOP_LEVEL_NEXT_STEP}" in output
        assert "Check the validation_errors array" not in output
        assert "Traceback" not in output

    def test_a_concept_mismatch_beside_a_multiplicity_one_reports_the_multiplicity(self, tmp_path: Path) -> None:
        """Of two faults in one combine, the caller's item is the multiplicity one, rendered from its own parameters."""
        problem = _verdict_problem(bundle_path=_write_bundle(directory=tmp_path, content=_TWO_FAULTS_IN_ONE_COMBINE))

        assert problem.errors is not None
        (item,) = problem.errors
        assert item.code == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert item.params is not None
        assert item.params.as_wire() == {"pipe": "analyze_topics", "output": "ideas", "declared": "single", "produced": "list"}
        assert item.detail == _LIST_INTO_SINGLE_SENTENCE
        # The combine's own text quotes the structure's validation, which is the operator's alone.
        assert "Error combining stuffs" not in str(problem.to_wire())

    @pytest.mark.parametrize(
        ("bundle_content", "pipe_code"),
        [(_TEXT_INTO_PRIMITIVE_LIST_FIELD, "analyze_topic"), (_ANYTHING_LIST_INTO_SINGLE_FIELD, "analyze_topics")],
        ids=["text_into_primitive_list_field", "anything_list_into_single_field"],
    )
    def test_no_multiplicity_advice_where_it_would_not_help(self, tmp_path: Path, bundle_content: str, pipe_code: str) -> None:
        """The verdict reports an output that does not fit its concept, never a multiplicity change that could not make it combine."""
        problem = _verdict_problem(bundle_path=_write_bundle(directory=tmp_path, content=bundle_content))

        assert problem.errors is not None
        (item,) = problem.errors
        assert item.code == CoreCode.PIPE_OUTPUT_INVALID
        assert item.params is not None
        assert item.params.as_wire() == {"pipe": pipe_code, "output_concept": "TopicReview", "fields": ["ideas"]}
        assert item.detail == f"Pipe '{pipe_code}' produced an output that does not fit the concept 'TopicReview', at the fields ideas."
        assert "Error combining stuffs" not in str(problem.to_wire())
        assert "cannot combine its branch results" not in str(problem.to_wire())

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
        problem = json.loads(capsys.readouterr().err)
        assert problem["is_valid"] is False
        assert problem["domain"] == "method"
        assert problem["code"] == CoreCode.METHOD_INVALID
        assert problem["next_step"]["kind"] == "change_method"
        (item,) = problem["errors"]
        assert item["location"]["pipe"] == "analyze_topics"
        assert item["detail"] == _LIST_INTO_SINGLE_SENTENCE

    def test_the_verdict_problem_carries_both_next_steps(self, tmp_path: Path) -> None:
        """The problem every surface draws from: the item names the fault, the top level points at the items."""
        bundle_path = _write_bundle(directory=tmp_path, content=_LIST_BRANCH_INTO_SINGLE_FIELD)

        with pytest.raises(ValidateBundleError) as raised:
            asyncio.run(validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent]))

        verdict = raised.value
        advice = verdict.advised_action()
        assert advice is not None
        assert (advice.detail or "").startswith(_TOP_LEVEL_NEXT_STEP)
        problem = verdict.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.next_step.kind == StepKind.CHANGE_METHOD
        assert problem.errors is not None
        (item,) = problem.errors
        assert item.code == CoreCode.PIPE_OUTPUT_MULTIPLICITY
        assert item.detail == _LIST_INTO_SINGLE_SENTENCE
        assert item.location is not None
        assert item.location.pipe == "analyze_topics"
