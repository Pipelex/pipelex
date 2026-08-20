from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.validation_error_types import PipeValidationErrorType

# Bundle declaring a domain concept that refines native.Text. The blueprint-layer guard at
# `PipeStructureBlueprint.validate_output` only catches literal Text strings (`"Text"`,
# `"native.Text"`, `"Text[]"`, `"Text[N]"`), so a domain concept that refines Text slips
# through to runtime validation and must be rejected by `validate_output_with_library`.
_REFINES_TEXT_MTHDS = """\
domain = "structure_outputs_test"
description = "Concept refining native.Text"

[concept]
RawDocument = { description = "A raw text document", refines = "native.Text" }
"""


class TestPipeStructureValidateOutputs:
    def test_output_refining_text_is_rejected_with_library(
        self,
        tmp_path: Path,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """A domain concept that `refines = "native.Text"` must be rejected as PipeStructure output
        by the runtime-library validator. The blueprint string-level check can't catch this case.
        """
        (tmp_path / "refines_text.mthds").write_text(_REFINES_TEXT_MTHDS, encoding="utf-8")
        load_test_library([tmp_path])

        blueprint = PipeStructureBlueprint(
            description="Bad output: refines Text",
            inputs={"draft_text": "native.Text"},
            output="structure_outputs_test.RawDocument",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="structure_outputs_test",
            pipe_code="struct_to_raw_document",
            blueprint=blueprint,
        )

        with pytest.raises(PipeValidationError) as exc_info:
            pipe_structure.validate_output_with_library()
        assert exc_info.value.error_type == PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
        assert exc_info.value.provided_concept_code == "structure_outputs_test.RawDocument"

    def test_structured_output_is_accepted(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Sanity: a non-Text output (Number is the canonical example used elsewhere) passes."""
        load_empty_library()
        blueprint = PipeStructureBlueprint(
            description="OK output",
            inputs={"draft_text": "native.Text"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="struct_to_number",
            blueprint=blueprint,
        )
        # Must not raise.
        pipe_structure.validate_output_with_library()
