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

# A branch whose declared output is plural but whose step carries a count of one: the resolved
# result is a single `PvAlt`, which the `tone_result` field (a `PvTone`) cannot hold. Reading the
# declaration alone skipped this check and let the mismatch reach `combine_stuffs` at run time.
_ONE_COUNT_PLURAL_BRANCH = """
[concept.PvTone]
description = "A tone reading"

[concept.PvTone.structure]
label = { type = "text", description = "The tone label", required = true }

[concept.PvAlt]
description = "Something a PvTone field cannot hold"

[concept.PvAlt.structure]
other = { type = "text", description = "An unrelated field", required = true }

[concept.PvComboTyped]
description = "Combined results whose fields are concept-typed"

[concept.PvComboTyped.structure]
tone_result   = { type = "concept", concept_ref = "PvTone", description = "Tone", required = true }
length_result = { type = "text", description = "Length", required = true }

[pipe.pv_branch_plural_alt]
type = "PipeLLM"
description = "Branch declaring a plural output"
inputs = { item = "PvItem" }
output = "PvAlt[]"
prompt = "Describe $item"

[pipe.pv_parallel_one_count]
type = "PipeParallel"
description = "Parallel whose plural branch carries a count of one"
inputs = { item = "PvItem" }
output = "PvComboTyped"
branches = [
  { pipe = "pv_branch_plural_alt", result = "tone_result", nb_output = 1 },
  { pipe = "pv_branch_length", result = "length_result" },
]
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

    def test_a_one_count_plural_branch_is_type_checked(self):
        """A plural branch with `nb_output = 1` resolves to the single form, so its type IS checked.

        Plurality is the run path's answer (declaration + step override). Skipping on the
        declaration alone let an incompatible singular result pass `/validate` and fail later in
        `StuffFactory.combine_stuffs`.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            acquire_library(library_id="pv_reject_one_count_plural_branch", mthds_contents=[_BUNDLE_HEADER + _ONE_COUNT_PLURAL_BRANCH])
        assert "tone_result" in str(exc_info.value)
