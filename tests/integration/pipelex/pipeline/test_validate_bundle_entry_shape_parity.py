"""Pin: the same bundle produces the same diagnostics whichever way it enters ``validate_bundle``.

``validate_bundle`` has two entry shapes — in-memory ``mthds_contents`` (what the HTTP
``/validate`` layer uses) and a ``mthds_file_path`` resolved against ``library_dirs`` (what the
CLI, and therefore the MTHDS Test Corpus entry-validation gate, uses). They are meant to be the
same check. They were not: the library-directory path ran through
``LibraryManager._load_mthds_files_into_library``, whose two exception arms both destroyed
structured error data on the way out, so a pipe/concept fault that the contents path reported as
a categorized item with an ``error_type`` came back as one untyped residual.

The gap was invisible because every structured-error test used the contents shape. This module
asserts the property directly instead: for each bundle, validate it both ways and require the
observed ``(category, error_type)`` list to match. It is the check that would have caught the
divergence, and the one that keeps a future wrapper from re-introducing it.

The bundles here are the two faults the loss actually reached — an unresolved concept reference
(raised as a ``ConceptLibraryError`` carrying per-reference items) and an optionals violation
(raised as a pydantic ``ValidationError`` during the merge) — plus one already-parity bundle, so
a fix that made the two shapes agree by making *both* untyped would still fail.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.validation_error_types import PipeValidationErrorType

_UNRESOLVED_CONCEPT_MTHDS = """
domain = "parity_unresolved_concept"
main_pipe = "tally_crates"

[pipe.tally_crates]
type = "PipeLLM"
description = "Count the crates listed on a manifest."
inputs = { manifest = "Text" }
output = "CrateTally"
prompt = "Count the crates listed on this manifest: $manifest"
"""

_OPTIONAL_INPUT_UNGUARDED_MTHDS = """
domain = "parity_optional_unguarded"
main_pipe = "write_delay_notice"

[pipe.write_delay_notice]
type = "PipeLLM"
description = "Write a delay notice that reaches for an optional platform without guarding it."
inputs = { service = "Text", platform = "Text?" }
output = "Text"
prompt = "The $service is delayed. It will leave from platform $platform."
"""

_MISSING_INPUT_VARIABLE_MTHDS = """
domain = "parity_missing_input"
main_pipe = "write_delay_notice"

[pipe.write_delay_notice]
type = "PipeLLM"
description = "Write a delay notice whose prompt reaches for an input it never declares."
inputs = { service = "Text" }
output = "Text"
prompt = "The $service is delayed and will leave from platform $platform."
"""


async def _observed_from_contents(mthds_contents: str) -> list[tuple[ValidationErrorCategory, str | None]]:
    with pytest.raises(ValidateBundleError) as raised:
        await validate_bundle(mthds_contents=[mthds_contents])
    return _observed(raised.value)


async def _observed_from_library_dir(mthds_contents: str, *, directory: Path) -> list[tuple[ValidationErrorCategory, str | None]]:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(mthds_contents, encoding="utf-8")
    with pytest.raises(ValidateBundleError) as raised:
        await validate_bundle(mthds_file_path=bundle_path, library_dirs=[directory])
    return _observed(raised.value)


def _observed(error: ValidateBundleError) -> list[tuple[ValidationErrorCategory, str | None]]:
    items = error.to_error_report().validation_errors or []
    return [(item.category, item.error_type) for item in items]


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleEntryShapeParity:
    @pytest.mark.parametrize(
        ("mthds_contents", "expected"),
        [
            pytest.param(
                _UNRESOLVED_CONCEPT_MTHDS,
                [(ValidationErrorCategory.PIPE_VALIDATION, PipeValidationErrorType.UNRESOLVED_CONCEPT)],
                id="unresolved_concept",
            ),
            pytest.param(
                _OPTIONAL_INPUT_UNGUARDED_MTHDS,
                [(ValidationErrorCategory.PIPE_VALIDATION, PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED)],
                id="optional_input_unguarded",
            ),
            pytest.param(
                _MISSING_INPUT_VARIABLE_MTHDS,
                [(ValidationErrorCategory.BLUEPRINT_VALIDATION, PipeValidationErrorType.MISSING_INPUT_VARIABLE)],
                id="missing_input_variable",
            ),
        ],
    )
    async def test_both_entry_shapes_report_the_same_categorized_errors(
        self,
        load_empty_library: Callable[[], str],
        tmp_path: Path,
        mthds_contents: str,
        expected: list[tuple[ValidationErrorCategory, str | None]],
    ) -> None:
        """Both shapes report the expected categorized items — and therefore each other's.

        Asserting each against the explicit expectation rather than only against one another is
        what stops the parity from being satisfiable by both shapes degrading together.
        """
        load_empty_library()
        from_contents = await _observed_from_contents(mthds_contents)
        assert from_contents == expected, f"contents shape produced {from_contents!r}"

        load_empty_library()
        from_library_dir = await _observed_from_library_dir(mthds_contents, directory=tmp_path)
        assert from_library_dir == expected, f"library-directory shape produced {from_library_dir!r}"
