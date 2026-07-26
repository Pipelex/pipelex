"""Static validation of a PipeParallel's declared output against its branch result names.

The declared output must be `Composite` or a structured concept whose fields are compatible with
the branch result names (required fields ⊆ result names; result names ⊆ declared fields). This is
enforced at library validation time so `/validate` surfaces it as an author-time error instead of
a runtime combine failure.
"""

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import clear_current_library, get_library_manager
from pipelex.pipeline.execution_seams import acquire_library

_BUNDLE_HEADER = """
domain = "pv_parallel_output"
description = "Static validation fixtures for PipeParallel output"

[concept.PvItem]
description = "An item to analyze"

[pipe.pv_branch_tone]
type = "PipeLLM"
description = "Tone branch"
inputs = { item = "PvItem" }
output = "Text"
prompt = "Describe the tone of $item"

[pipe.pv_branch_length]
type = "PipeLLM"
description = "Length branch"
inputs = { item = "PvItem" }
output = "Text"
prompt = "Describe the length of $item"
"""

_PARALLEL_TEMPLATE = """
[pipe.pv_parallel]
type = "PipeParallel"
description = "Parallel under test"
inputs = {{ item = "PvItem" }}
output = "{output}"
branches = [
  {{ pipe = "pv_branch_tone", result = "tone_result" }},
  {{ pipe = "pv_branch_length", result = "length_result" }},
]
"""

_CONCEPT_EXACT_MATCH = """
[concept.PvCombo]
description = "Combined results"

[concept.PvCombo.structure]
tone_result   = { type = "text", description = "Tone", required = true }
length_result = { type = "text", description = "Length", required = true }
"""

_CONCEPT_WITH_OPTIONAL_EXTRA = """
[concept.PvComboLoose]
description = "Combined results with an optional extra field"

[concept.PvComboLoose.structure]
tone_result   = { type = "text", description = "Tone", required = true }
length_result = { type = "text", description = "Length", required = true }
notes         = { type = "text", description = "Optional notes", required = false }
"""

_CONCEPT_MISSING_REQUIRED = """
[concept.PvComboStrict]
description = "Combined results requiring a field no branch produces"

[concept.PvComboStrict.structure]
tone_result   = { type = "text", description = "Tone", required = true }
length_result = { type = "text", description = "Length", required = true }
verdict       = { type = "text", description = "Required field no branch produces", required = true }
"""

_CONCEPT_MISSING_DECLARED_FIELD = """
[concept.PvComboNarrow]
description = "Combined results lacking a field for one branch result"

[concept.PvComboNarrow.structure]
tone_result = { type = "text", description = "Tone", required = true }
"""

_CONCEPT_DESCRIPTION_ONLY = """
[concept.PvComboImplicit]
description = "A description-only concept (implicitly text-shaped)"
"""


def _bundle(*, output: str, extra_concepts: str = "") -> str:
    return _BUNDLE_HEADER + extra_concepts + _PARALLEL_TEMPLATE.format(output=output)


class TestPipeParallelOutputValidation:
    @pytest.mark.parametrize(
        ("test_id", "mthds_content"),
        [
            ("composite_output", _bundle(output="Composite")),
            ("structured_exact_match", _bundle(output="PvCombo", extra_concepts=_CONCEPT_EXACT_MATCH)),
            ("structured_with_optional_extra", _bundle(output="PvComboLoose", extra_concepts=_CONCEPT_WITH_OPTIONAL_EXTRA)),
        ],
    )
    def test_accepted_outputs(self, test_id: str, mthds_content: str):
        library_manager = get_library_manager()
        library_id = f"pv_accept_{test_id}"
        acquire_library(library_id=library_id, mthds_contents=[mthds_content])
        try:
            pass  # loading without raising IS the assertion
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    @pytest.mark.parametrize(
        ("test_id", "mthds_content", "expected_fragment"),
        [
            (
                "missing_required_field",
                _bundle(output="PvComboStrict", extra_concepts=_CONCEPT_MISSING_REQUIRED),
                "verdict",
            ),
            (
                "result_name_not_declared",
                _bundle(output="PvComboNarrow", extra_concepts=_CONCEPT_MISSING_DECLARED_FIELD),
                "length_result",
            ),
            (
                "description_only_concept",
                _bundle(output="PvComboImplicit", extra_concepts=_CONCEPT_DESCRIPTION_ONLY),
                "text",
            ),
        ],
    )
    def test_rejected_outputs(self, test_id: str, mthds_content: str, expected_fragment: str):
        with pytest.raises(PipeValidationError) as exc_info:
            acquire_library(library_id=f"pv_reject_{test_id}", mthds_contents=[mthds_content])
        assert expected_fragment in str(exc_info.value)
