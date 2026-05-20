from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_library_manager
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint

# Bundle that declares a domain concept refining native.Text. Used to verify that
# `validate_inputs_with_library` accepts Text-refining concepts at the strict=False level.
_REFINES_TEXT_MTHDS = """\
domain = "structure_inputs_test"
description = "Concept refining native.Text"

[concept]
RawDocument = { description = "A raw text document", refines = "native.Text" }
"""


class TestPipeStructureValidateInputs:
    def test_non_text_input_raises_input_stuff_spec_mismatch(
        self,
        load_empty_library: Callable[[], str],
    ) -> None:
        """The single input is present but its concept is not Text-compatible.

        The error must be classified as INPUT_STUFF_SPEC_MISMATCH (the spec doesn't match),
        not MISSING_INPUT_VARIABLE (which would lie — the variable IS there).
        """
        load_empty_library()
        blueprint = PipeStructureBlueprint(
            description="Structure draft text",
            inputs={"draft_text": "native.Image"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="struct_with_image_input",
            blueprint=blueprint,
        )

        with pytest.raises(PipeValidationError) as exc_info:
            pipe_structure.validate_inputs_with_library()
        assert exc_info.value.error_type == PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
        assert exc_info.value.provided_concept_code == "native.Image"

    def test_input_refining_text_is_accepted(
        self,
        tmp_path: Path,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """A domain concept that `refines = "native.Text"` must be accepted as a PipeStructure input."""
        (tmp_path / "refines_text.mthds").write_text(_REFINES_TEXT_MTHDS, encoding="utf-8")
        load_test_library([tmp_path])

        blueprint = PipeStructureBlueprint(
            description="Structure a raw document",
            inputs={"draft_text": "structure_inputs_test.RawDocument"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="structure_inputs_test",
            pipe_code="struct_from_raw_document",
            blueprint=blueprint,
        )

        pipe_structure.validate_inputs_with_library()

        library = get_library_manager().get_current_library()
        raw_doc_concept = library.concept_library.get_required_concept(concept_ref="structure_inputs_test.RawDocument")
        assert raw_doc_concept.refines == "native.Text"
