"""Pin: every refusal raised while loading a bundle is a verdict item, never a no-verdict fault.

A bundle validator answers either a verdict (valid, or invalid with located items) or "no verdict could
be produced", which is reserved for a failure of the tool or its environment. These tests load real
bundles through ``validate_bundle`` and pin the verdict each refusal produces:

- **The unknown model, per pipe type and per reference kind.** A pipe whose model field names a handle,
  an alias or a preset the deck does not define validates to one ``pipe_validation`` item with the
  closed ``error_type`` ``unknown_model``, carrying the pipe, the domain, the source file, the field
  path, the reference as written, the model type and the deck's suggestions, and a ``rename-model`` fix
  when the deck offers exactly one suggestion. Every pipe type that names a model gives the same item
  (``PipeExtract`` and ``PipeSearch`` used to turn it into an ``unknown_validation_error`` whose message
  was a Python repr).
- **The general arm.** Any other ``input``-domained refusal raised while building a pipe validates to one
  item located on the pipe and its file, keeping its message only when it is caller-facing; a
  ``config``-domained fault raised at the same place still propagates as no verdict.
- **The run path.** Setting up a run on the unknown-model bundle refuses it with an error naming the
  pipe, whose STRICT projection is still an HTTP 422 carrying the deck check's sentence.

The deck is the test session's own, so the suggestion lists are read off it rather than pinned in
full, except for the one-suggestion alias whose rename fix is the point of its case.
"""

from pathlib import Path
from typing import ClassVar, NamedTuple

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.planner import RENAME_MODEL_FIX_CODE
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.suggested_fix import RemapValueOp
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

_DOMAIN = "tide_tables"


def _llm_bundle(*, model_line: str) -> str:
    return f"""
domain      = "{_DOMAIN}"
description = "Write the note telling harbour users when the tide turns"
main_pipe   = "write_tide_note"

[pipe.write_tide_note]
type        = "PipeLLM"
description = "Write the tide note for the harbour board"
inputs      = {{ tide_times = "Text" }}
output      = "Text"
{model_line}
prompt      = "Write a short note for the harbour board from these tide times: $tide_times"
"""


_IMG_GEN_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Draw the board announcing the tide times"
main_pipe   = "draw_tide_board"

[pipe.draw_tide_board]
type        = "PipeImgGen"
description = "Draw the painted board announcing the tide times"
output      = "Image"
model       = "nano-banana-9"
prompt      = "A painted wooden harbour board announcing the tide times, morning light"
"""

_EXTRACT_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Read the pages of a printed tide almanac"
main_pipe   = "read_almanac_pages"

[pipe.read_almanac_pages]
type        = "PipeExtract"
description = "Read each page of a scanned tide almanac"
inputs      = {{ almanac_scan = "Document" }}
output      = "Page[]"
model       = "@default-extrct"
"""

_SEARCH_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Look up the tide times of a harbour"
main_pipe   = "look_up_tides"

[pipe.look_up_tides]
type        = "PipeSearch"
description = "Look up today's tide times for the harbour"
inputs      = {{ harbour_name = "Text" }}
output      = "SearchResult"
model       = "@default-serch"
prompt      = "What are today's tide times at $harbour_name?"
"""


class _UnknownModelCase(NamedTuple):
    case_id: str
    bundle: str
    pipe_code: str
    field_name: str
    model_reference: str
    model_type: str
    model_sentence: str


_UNKNOWN_MODEL_CASES: list[_UnknownModelCase] = [
    _UnknownModelCase(
        case_id="llm_handle",
        bundle=_llm_bundle(model_line='model       = "gpt-5.1"'),
        pipe_code="write_tide_note",
        field_name="model",
        model_reference="gpt-5.1",
        model_type="llm",
        model_sentence="Model handle 'gpt-5.1' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="llm_alias",
        bundle=_llm_bundle(model_line='model       = "@best-sonet"'),
        pipe_code="write_tide_note",
        field_name="model",
        model_reference="@best-sonet",
        model_type="llm",
        model_sentence="Alias 'best-sonet' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="llm_preset",
        bundle=_llm_bundle(model_line='model       = "$writting-factual"'),
        pipe_code="write_tide_note",
        field_name="model",
        model_reference="$writting-factual",
        model_type="llm",
        model_sentence="LLM preset 'writting-factual' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="llm_model_to_structure",
        bundle=_llm_bundle(model_line='model_to_structure = "@best-sonet"'),
        pipe_code="write_tide_note",
        field_name="model_to_structure",
        model_reference="@best-sonet",
        model_type="llm",
        model_sentence="Alias 'best-sonet' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="img_gen_handle",
        bundle=_IMG_GEN_BUNDLE,
        pipe_code="draw_tide_board",
        field_name="model",
        model_reference="nano-banana-9",
        model_type="img_gen",
        model_sentence="Model handle 'nano-banana-9' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="extract_alias",
        bundle=_EXTRACT_BUNDLE,
        pipe_code="read_almanac_pages",
        field_name="model",
        model_reference="@default-extrct",
        model_type="text_extractor",
        model_sentence="Alias 'default-extrct' was not found in the model deck",
    ),
    _UnknownModelCase(
        case_id="search_alias",
        bundle=_SEARCH_BUNDLE,
        pipe_code="look_up_tides",
        field_name="model",
        model_reference="@default-serch",
        model_type="search",
        model_sentence="Alias 'default-serch' was not found in the model deck",
    ),
]


def _write_bundle(*, directory: Path, content: str) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
    return bundle_path


async def _single_item(*, bundle_path: Path) -> ValidationErrorItem:
    with pytest.raises(ValidateBundleError) as raised:
        await validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent])
    items = raised.value.to_error_report().validation_errors or []
    assert len(items) == 1, f"expected exactly one item, got {items!r}"
    return items[0]


class _CallerFacingRefusalError(PipelexError):
    """An input refusal whose message was authored for the caller — stands in for any future one."""

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True


class _InternalInputRefusalError(PipelexError):
    """An input refusal whose message is internal text the verdict must not carry."""

    error_domain = ErrorDomain.INPUT
    _declared_title: ClassVar[str | None] = "Harbour board refusal"


class _ConfigFaultError(PipelexError):
    """A fault of the environment, which is no verdict about the bundle."""

    error_domain = ErrorDomain.CONFIG


@pytest.mark.asyncio(loop_scope="class")
class TestValidateBundleLoadRefusals:
    @pytest.mark.parametrize("case", _UNKNOWN_MODEL_CASES, ids=[case.case_id for case in _UNKNOWN_MODEL_CASES])
    async def test_unknown_model_is_one_located_unknown_model_item(self, case: _UnknownModelCase, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=case.bundle)

        item = await _single_item(bundle_path=bundle_path)

        assert item.category == ValidationErrorCategory.PIPE_VALIDATION
        assert item.error_type == PipeValidationErrorType.UNKNOWN_MODEL
        assert item.pipe_code == case.pipe_code
        assert item.domain_code == _DOMAIN
        assert item.source == str(bundle_path)
        assert item.field_name == case.field_name
        assert item.field_path == f"pipe.{case.pipe_code}.{case.field_name}"
        assert item.model_reference == case.model_reference
        assert item.model_type == case.model_type
        assert case.model_sentence in item.message
        assert f"Pipe '{case.pipe_code}'" in item.message
        # The suggestions ride as a list and stay in the message, for the consumers that keep only it.
        assert item.suggestions, f"the deck offers no close match for {case.model_reference!r}"
        for suggestion in item.suggestions:
            assert suggestion in item.message

    async def test_one_suggestion_carries_a_rename_fix(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_llm_bundle(model_line='model       = "@best-sonet"'))

        item = await _single_item(bundle_path=bundle_path)

        assert item.suggestions == ["@best-gpt"]
        fix = item.suggested_fix
        assert fix is not None
        assert fix.fix_code == RENAME_MODEL_FIX_CODE
        assert fix.safety.is_safe
        assert fix.source == str(bundle_path)
        assert fix.ops == [RemapValueOp(table_path=["pipe", "write_tide_note"], key="model", mapping={"@best-sonet": "@best-gpt"})]

    async def test_several_suggestions_carry_no_fix(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_llm_bundle(model_line='model       = "$writting-factual"'))

        item = await _single_item(bundle_path=bundle_path)

        assert item.suggestions is not None
        assert len(item.suggestions) > 1
        assert item.suggested_fix is None

    async def test_caller_facing_input_refusal_at_load_is_a_located_item(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.pipe_operators.llm.pipe_llm.check_llm_choice_with_deck",
            side_effect=_CallerFacingRefusalError("The harbour board cannot show tides this far upriver."),
        )
        bundle_path = _write_bundle(directory=tmp_path, content=_llm_bundle(model_line='model       = "@best-gpt"'))

        item = await _single_item(bundle_path=bundle_path)

        assert item.category == ValidationErrorCategory.PIPE_VALIDATION
        assert item.error_type is None
        assert item.pipe_code == "write_tide_note"
        assert item.domain_code == _DOMAIN
        assert item.source == str(bundle_path)
        assert "The harbour board cannot show tides this far upriver." in item.message

    async def test_internal_input_refusal_carries_its_title_not_its_message(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.pipe_operators.llm.pipe_llm.check_llm_choice_with_deck",
            side_effect=_InternalInputRefusalError("internal detail: registry slot 7 is stale"),
        )
        bundle_path = _write_bundle(directory=tmp_path, content=_llm_bundle(model_line='model       = "@best-gpt"'))

        item = await _single_item(bundle_path=bundle_path)

        assert item.pipe_code == "write_tide_note"
        assert item.source == str(bundle_path)
        assert "Harbour board refusal" in item.message
        assert "registry slot 7" not in item.message

    async def test_config_fault_at_load_stays_no_verdict(self, tmp_path: Path, mocker: MockerFixture) -> None:
        fault = _ConfigFaultError("the model deck could not be read")
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.check_llm_choice_with_deck", side_effect=fault)
        bundle_path = _write_bundle(directory=tmp_path, content=_llm_bundle(model_line='model       = "@best-gpt"'))

        with pytest.raises(_ConfigFaultError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[bundle_path.parent])

        assert raised.value is fault

    async def test_run_setup_refuses_the_unknown_model_naming_the_pipe(self) -> None:
        execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)

        with pytest.raises(PipeOperatorModelChoiceError) as raised:
            await pipeline_run_setup(
                storage_scope="test/scope",
                user_id="test-user",
                execution_config=execution_config,
                mthds_contents=[_llm_bundle(model_line='model       = "gpt-5.1"')],
                pipe_code="write_tide_note",
                pipe_run_mode=PipeRunMode.DRY,
            )

        error = raised.value
        assert error.pipe_code == "write_tide_note"
        assert error.field_name == "model"
        report = error.to_error_report()
        assert report.http_status == 422
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["error_type"] == "PipeOperatorModelChoiceError"
        assert strict_payload["error_domain"] == "input"
        assert "Pipe 'write_tide_note'" in strict_payload["message"]
        assert "Model handle 'gpt-5.1' was not found in the model deck" in strict_payload["message"]
