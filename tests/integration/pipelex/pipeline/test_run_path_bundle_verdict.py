"""Pin: the run path refuses an invalid bundle with the verdict ``validate`` gives for it.

A run loads its bundle before any pipe runs, and that load already refuses an invalid method. These tests
pin that the refusal reaches the caller the way validating the same bundle reports it: a
``ValidateBundleError`` carrying the same located ``validation_errors`` items, whose STRICT projection is
an HTTP 422 that keeps them. Before, each refusal reached a host in the raw class of whichever check
made it: a misspelled concept as a ``ConceptLibraryError`` answered 500, a wiring mismatch as a
``PipeValidationError`` (a ``ValueError``) answered by the catch-all 500, a TOML fault as a 422 with no
items, and a check firing inside a pipe's pydantic validator as a ``runtime`` ``PipeExecutionError``
reading "Input validation failed".

- **Parity.** For each bundle, ``pipeline_run_setup`` raises the verdict with exactly the items
  ``validate_bundle`` produces, and the STRICT projection is a 422 carrying them.
- **The model-validator case.** The runner's ``execute`` answers it with the verdict, not with the
  ``runtime`` input-validation failure.
- **The unknown entry pipe** is not a bundle fault: it still raises its own ``PipeNotFoundError``.
- **Whose library directories.** A local caller's directories are theirs, so a refusal while loading
  them is the verdict too, located on their file; a host's directories load untranslated by default.
"""

from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pipelex.base_exceptions import DisclosureMode
from pipelex.config import get_config
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipeline.exceptions import PipeExecutionError, ValidateBundleError
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

_MISSPELLED_CONCEPT_BUNDLE = """
domain      = "harbour_notices"
description = "Write notices for the harbour board"
main_pipe   = "write_tide_notice"

[concept.TideNotice]
description = "A notice telling harbour users when the tide turns"

[pipe.write_tide_notice]
type        = "PipeLLM"
description = "Write the tide notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "TideNotise"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

_SEQUENCE_OUTPUT_MISMATCH_BUNDLE = """
domain      = "harbour_notices"
description = "Write notices for the harbour board"
main_pipe   = "prepare_notices"

[pipe.prepare_notices]
type        = "PipeSequence"
description = "Prepare the notices for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text[]"
steps       = [{ pipe = "write_tide_notice", result = "tide_notice" }]

[pipe.write_tide_notice]
type        = "PipeLLM"
description = "Write the tide notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""

_TOML_SYNTAX_ERROR_BUNDLE = """
domain      = "harbour_notices
description = "Write notices for the harbour board"
"""

# A field value the blueprint schema refuses and no categorizer names: the item carries no error_type.
_UNCATEGORIZED_BLUEPRINT_FAULT_BUNDLE = """
domain      = "harbour_notices"
description = "Draw the harbour board"
main_pipe   = "draw_harbour_board"

[pipe.draw_harbour_board]
type         = "PipeImgGen"
description  = "Draw the painted harbour board"
output       = "Image"
prompt       = "A painted wooden harbour board announcing the tide times"
aspect_ratio = "7:3"
"""

# A check that fires inside a pipe's pydantic validator while the pipe is built: the function a
# PipeFunc names is not registered.
_MODEL_VALIDATOR_FAULT_BUNDLE = """
domain        = "harbour_notices"
description   = "Format notices for the harbour board"
main_pipe     = "format_tide_notice"

[pipe.format_tide_notice]
type          = "PipeFunc"
description   = "Format the tide notice for the harbour board"
inputs        = { tide_times = "Text" }
output        = "Text"
function_name = "format_harbour_tide_notice_nowhere_registered"
"""

_VALID_BUNDLE = """
domain      = "harbour_notices"
description = "Write notices for the harbour board"
main_pipe   = "write_tide_notice"

[pipe.write_tide_notice]
type        = "PipeLLM"
description = "Write the tide notice for the harbour board"
inputs      = { tide_times = "Text" }
output      = "Text"
prompt      = "Write a short notice for the harbour board from these tide times: $tide_times"
"""


class _InvalidBundleCase(NamedTuple):
    case_id: str
    bundle: str


_INVALID_BUNDLE_CASES: list[_InvalidBundleCase] = [
    _InvalidBundleCase(case_id="misspelled_concept", bundle=_MISSPELLED_CONCEPT_BUNDLE),
    _InvalidBundleCase(case_id="sequence_output_mismatch", bundle=_SEQUENCE_OUTPUT_MISMATCH_BUNDLE),
    _InvalidBundleCase(case_id="toml_syntax_error", bundle=_TOML_SYNTAX_ERROR_BUNDLE),
    _InvalidBundleCase(case_id="uncategorized_blueprint_fault", bundle=_UNCATEGORIZED_BLUEPRINT_FAULT_BUNDLE),
    _InvalidBundleCase(case_id="model_validator_fault", bundle=_MODEL_VALIDATOR_FAULT_BUNDLE),
]


def _execution_config() -> PipelineExecutionConfig:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, generate_usage=False, mock_inputs=True)


async def _validate_verdict(*, bundle: str) -> ValidateBundleError:
    with pytest.raises(ValidateBundleError) as raised:
        await validate_bundle(mthds_contents=[bundle])
    return raised.value


async def _run_setup(**kwargs: Any) -> None:
    await pipeline_run_setup(
        storage_scope="test/scope",
        user_id="test-user",
        execution_config=_execution_config(),
        pipe_run_mode=PipeRunMode.DRY,
        **kwargs,
    )


def _strict_items(verdict: ValidateBundleError) -> list[dict[str, Any]]:
    strict_payload = verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
    strict_items: list[dict[str, Any]] = strict_payload["validation_errors"]
    return strict_items


@pytest.mark.asyncio(loop_scope="class")
class TestRunPathBundleVerdict:
    @pytest.mark.parametrize("case", _INVALID_BUNDLE_CASES, ids=[case.case_id for case in _INVALID_BUNDLE_CASES])
    async def test_run_setup_refuses_with_the_validate_verdict(self, case: _InvalidBundleCase) -> None:
        validate_verdict = await _validate_verdict(bundle=case.bundle)

        with pytest.raises(ValidateBundleError) as raised:
            await _run_setup(mthds_contents=[case.bundle])

        run_report = raised.value.to_error_report()
        validate_items = validate_verdict.to_error_report().validation_errors
        assert validate_items, "the validate path gives at least one item for an invalid bundle"
        assert run_report.validation_errors == validate_items
        assert run_report.http_status == 422
        strict_payload = run_report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["error_type"] == "ValidateBundleError"
        assert strict_payload["error_domain"] == "input"
        assert _strict_items(raised.value) == _strict_items(validate_verdict)

    async def test_misspelled_concept_is_located_on_the_pipe_and_the_field(self) -> None:
        with pytest.raises(ValidateBundleError) as raised:
            await _run_setup(mthds_contents=[_MISSPELLED_CONCEPT_BUNDLE])

        items = raised.value.to_error_report().validation_errors or []
        (item,) = items
        assert item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT
        assert item.pipe_code == "write_tide_notice"
        assert item.concept_code == "TideNotise"
        assert item.field_path == "pipe.write_tide_notice.output"
        # The run request names no file, so the item carries no source — never a host path.
        assert item.source is None

    async def test_execute_answers_a_model_validator_fault_with_the_verdict(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=_execution_config())

        with pytest.raises(ValidateBundleError) as raised:
            await runner.execute(mthds_contents=[_MODEL_VALIDATOR_FAULT_BUNDLE])

        assert not isinstance(raised.value, PipeExecutionError)
        items = raised.value.to_error_report().validation_errors or []
        assert any("format_harbour_tide_notice_nowhere_registered" in item.message for item in items)

    async def test_unknown_entry_pipe_keeps_its_own_class(self) -> None:
        with pytest.raises(PipeNotFoundError) as raised:
            await _run_setup(mthds_contents=[_VALID_BUNDLE], pipe_code="write_harbour_poem")

        assert not isinstance(raised.value, ValidateBundleError)

    async def test_a_callers_library_dir_refusal_is_the_verdict_located_on_their_file(self, tmp_path: Path) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_MISSPELLED_CONCEPT_BUNDLE, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as raised:
            await _run_setup(library_dirs=[str(tmp_path)], pipe_code="write_tide_notice", library_dirs_are_callers=True)

        items = raised.value.to_error_report().validation_errors or []
        concept_items = [item for item in items if item.error_type == PipeValidationErrorType.UNRESOLVED_CONCEPT]
        assert concept_items, f"expected an unresolved_concept item, got {items!r}"
        assert all(item.pipe_code == "write_tide_notice" for item in concept_items)
        # Validating the same file with the same library directory gives the same items.
        with pytest.raises(ValidateBundleError) as validated:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])
        assert items == validated.value.to_error_report().validation_errors

    async def test_a_hosts_library_dir_refusal_loads_untranslated_by_default(self, tmp_path: Path) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(_MISSPELLED_CONCEPT_BUNDLE, encoding="utf-8")

        with pytest.raises(LibraryError) as raised:
            await _run_setup(library_dirs=[str(tmp_path)], pipe_code="write_tide_notice")

        assert not isinstance(raised.value, ValidateBundleError)
