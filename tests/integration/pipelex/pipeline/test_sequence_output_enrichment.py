"""Pin: PipeSequence output-mismatch errors carry the expected output ref (autofix enrichment).

The validator already knows the correct sequence output at detection time — the last
step's effective output. These tests pin that ``INADEQUATE_OUTPUT_CONCEPT`` /
``INADEQUATE_OUTPUT_MULTIPLICITY`` raised by ``PipeSequence.validate_output_with_library``
carry it as ``expected_output_ref`` on the categorized error data, in full bundle
representation: concept (bare code when same-domain or native, qualified otherwise) +
multiplicity (honoring the sub-pipe ``output_multiplicity`` override) + presence marker.
This enriched fact is what the fix planner translates into a ``match-sequence-output``
suggested fix.
"""

from collections.abc import Callable

import pytest

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

_WRONG_CONCEPT_MTHDS = """
domain = "seqfix_concept"
main_pipe = "make_summary"

[concept]
Summary = "A summary of a text."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Sequence declaring an incompatible output concept (Number vs the last step's Summary)."
inputs = { text = "Text" }
output = "Number"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_WRONG_MULTIPLICITY_MTHDS = """
domain = "seqfix_mult"
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

_OVERRIDE_MULTIPLICITY_MTHDS = """
domain = "seqfix_override"
main_pipe = "pick_three"

[concept]
Idea = "An idea."

[pipe.gen_idea]
type = "PipeLLM"
description = "Generate one idea."
inputs = { topic = "Text" }
output = "Idea"
prompt = "One idea about $topic"

[pipe.pick_three]
type = "PipeSequence"
description = "Sequence whose last step carries an output_multiplicity override."
inputs = { topic = "Text" }
output = "Idea"
steps = [
  { pipe = "gen_idea", result = "ideas", nb_output = 3 },
]
"""

_OPTIONAL_MARKER_MTHDS = """
domain = "seqfix_optional"
main_pipe = "gated_check"

[concept]
Verdict = "A verdict."

[pipe.check]
type = "PipeLLM"
description = "Check the doc."
inputs = { doc = "Text" }
output = "Verdict"
prompt = "Check $doc"

[pipe.gate]
type = "PipeCondition"
description = "Gate that may continue with no output."
inputs = { doc = "Text" }
output = "Verdict?"
expression = "doc"
default_outcome = "continue"

[pipe.gate.outcomes]
go = "check"

[pipe.gated_check]
type = "PipeSequence"
description = "Sequence declaring the wrong concept while the last step's output is optional."
inputs = { doc = "Text" }
output = "Number"
steps = [
  { pipe = "gate", result = "verdict" },
]
"""

_TAINTED_OPTIONAL_BOUNDARY_MTHDS = """
domain = "seqfix_tainted_boundary"
main_pipe = "make_summary"

[concept]
Summary = "A summary."

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize text."
inputs = { text = "Text" }
output = "Summary"
prompt = "Summarize $text"

[pipe.make_summary]
type = "PipeSequence"
description = "Lift over optional input while declaring the wrong output concept."
inputs = { text = "Text?" }
output = "Number?"
steps = [
  { pipe = "write_summary", result = "summary" },
]
"""

_PLURAL_OUTPUT_WITH_OPTIONAL_DECLARATION_MTHDS = """
domain = "seqfix_plural_presence"
main_pipe = "make_ideas"

[concept]
Idea = "An idea."

[pipe.write_idea]
type = "PipeLLM"
description = "Write one idea."
inputs = { topic = "Text" }
output = "Idea"
prompt = "Write one idea about $topic"

[pipe.make_ideas]
type = "PipeSequence"
description = "Declare an optional wrong concept while the last step produces a list."
inputs = { topic = "Text" }
output = "Number?"
steps = [
  { pipe = "write_idea", result = "ideas", nb_output = 3 },
]
"""


async def _enriched_error_data_for(
    mthds_content: str,
    *,
    error_type: PipeValidationErrorType,
) -> PipesAndConceptValidationErrorData:
    """Validate one invalid bundle and return its single enriched pipe-validation error data."""
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[mthds_content])
    matching = [error_data for error_data in exc_info.value.pipe_validation_error_data if error_data.error_type == error_type]
    assert matching, f"Expected a {error_type} error, got {[(e.error_type, e.pipe_code) for e in exc_info.value.pipe_validation_error_data]}"
    return matching[0]


@pytest.mark.asyncio(loop_scope="class")
class TestSequenceOutputEnrichment:
    async def test_wrong_concept_carries_expected_output_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A concept mismatch carries the last step's output as the expected ref, bare same-domain code."""
        load_empty_library()
        error_data = await _enriched_error_data_for(_WRONG_CONCEPT_MTHDS, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT)
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_output_ref == "Summary"

    async def test_wrong_multiplicity_carries_expected_output_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A multiplicity mismatch carries the last step's output ref including its `[]` suffix."""
        load_empty_library()
        error_data = await _enriched_error_data_for(_WRONG_MULTIPLICITY_MTHDS, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert error_data.pipe_code == "list_ideas"
        assert error_data.expected_output_ref == "Idea[]"

    async def test_sub_pipe_multiplicity_override_wins_in_expected_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """The sub-pipe's ``nb_output`` override defines the effective expected multiplicity (`[3]`)."""
        load_empty_library()
        error_data = await _enriched_error_data_for(_OVERRIDE_MULTIPLICITY_MTHDS, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY)
        assert error_data.pipe_code == "pick_three"
        assert error_data.expected_output_ref == "Idea[3]"

    async def test_optional_marker_rides_expected_output_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A last step with an optional (`?`) output keeps its presence marker in the expected ref."""
        load_empty_library()
        error_data = await _enriched_error_data_for(_OPTIONAL_MARKER_MTHDS, error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT)
        assert error_data.pipe_code == "gated_check"
        assert error_data.expected_output_ref == "Verdict?"

    async def test_sequence_taint_preserves_optional_boundary_in_expected_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A lifted singular last step keeps the sequence boundary's valid optional marker."""
        load_empty_library()
        error_data = await _enriched_error_data_for(
            _TAINTED_OPTIONAL_BOUNDARY_MTHDS,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        )
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_output_ref == "Summary?"

    async def test_sequence_taint_adds_optional_boundary_to_plain_expected_ref(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Taint makes the singular expected ref optional even when the wrong declaration is plain."""
        load_empty_library()
        mthds_content = _TAINTED_OPTIONAL_BOUNDARY_MTHDS.replace('output = "Number?"', 'output = "Number"')
        error_data = await _enriched_error_data_for(
            mthds_content,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        )
        assert error_data.pipe_code == "make_summary"
        assert error_data.expected_output_ref == "Summary?"

    async def test_plural_expected_output_drops_optional_presence_marker(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """A multiplicity override never combines the plural expected ref with `?`."""
        load_empty_library()
        error_data = await _enriched_error_data_for(
            _PLURAL_OUTPUT_WITH_OPTIONAL_DECLARATION_MTHDS,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
        )
        assert error_data.pipe_code == "make_ideas"
        assert error_data.expected_output_ref == "Idea[3]"
