"""Pin: a pipe factory's refusal, and a refusal raised while the builder's validate ops load libraries, is a verdict.

A pipe factory refuses a blueprint it cannot build, such as a ``PipeExtract`` whose input is neither an
image nor a document. Its error classes declared no domain, so the validation translation did not
recognise them and they escaped every validator raw. They are now the author's input, caller-facing, so
the refusal validates to one item located on the pipe and its file, carrying the next step. The builder's
``validate_ops.validate_pipe`` and ``validate_all`` loaded libraries outside the translation, so a refusal
there escaped raw too; they now answer it with the same verdict.
"""

from pathlib import Path

import pytest

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.builder.operations.validate_ops import validate_all, validate_pipe
from pipelex.core.pipes.exceptions import PipeLoadRefusalError
from pipelex.pipe_controllers.condition.exceptions import PipeConditionFactoryError
from pipelex.pipe_controllers.parallel.exceptions import PipeParallelFactoryError
from pipelex.pipe_operators.compose.exceptions import PipeComposeFactoryError
from pipelex.pipe_operators.extract.exceptions import PipeExtractFactoryError
from pipelex.pipe_operators.llm.exceptions import PipeLLMFactoryError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle

_DOMAIN = "almanac_reading"

_TEXT_INPUT_EXTRACT_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Read the pages of a tide almanac"
main_pipe   = "read_almanac_pages"

[pipe.read_almanac_pages]
type        = "PipeExtract"
description = "Read each page of the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Page[]"
"""

_NEXT_STEP = "Declare this input as an Image or a Document, or as a concept that refines one of them."

_FACTORY_REFUSAL_CLASSES: list[type[PipelexError]] = [
    PipeLLMFactoryError,
    PipeComposeFactoryError,
    PipeExtractFactoryError,
    PipeConditionFactoryError,
    PipeParallelFactoryError,
]


def _write_bundle(*, directory: Path) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(_TEXT_INPUT_EXTRACT_BUNDLE, encoding="utf-8")
    return bundle_path


def _assert_located_extract_item(*, items: list[ValidationErrorItem], bundle_path: Path) -> None:
    (item,) = items
    assert item.category == ValidationErrorCategory.PIPE_VALIDATION
    assert item.pipe_code == "read_almanac_pages"
    assert item.domain_code == _DOMAIN
    assert item.source == str(bundle_path)
    assert "The input 'almanac_text' of PipeExtract 'read_almanac_pages' is a native.Text" in item.message
    assert _NEXT_STEP in item.message


@pytest.mark.asyncio(loop_scope="class")
class TestFactoryRefusalVerdicts:
    @pytest.mark.parametrize("error_class", _FACTORY_REFUSAL_CLASSES, ids=[error_class.__name__ for error_class in _FACTORY_REFUSAL_CLASSES])
    async def test_factory_refusal_is_the_authors_caller_facing_input(self, error_class: type[PipelexError]) -> None:
        report = error_class("The pipe cannot be built from this blueprint.").to_error_report()

        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message
        assert report.http_status == 422

    async def test_validate_bundle_locates_the_extract_refusal_with_its_next_step(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        assert isinstance(raised.value.__cause__, PipeLoadRefusalError)
        assert isinstance(raised.value.__cause__.__cause__, PipeExtractFactoryError)
        report = raised.value.to_error_report()
        _assert_located_extract_item(items=report.validation_errors or [], bundle_path=bundle_path)
        (strict_item,) = report.to_dict(disclosure_mode=DisclosureMode.STRICT)["validation_errors"]
        assert _NEXT_STEP in strict_item["message"]

    async def test_validate_ops_validate_pipe_answers_a_load_refusal_with_the_verdict(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_pipe("read_almanac_pages", library_dirs=[tmp_path])

        _assert_located_extract_item(items=raised.value.to_error_report().validation_errors or [], bundle_path=bundle_path)

    async def test_validate_ops_validate_all_answers_a_load_refusal_with_the_verdict(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_all(library_dirs=[tmp_path])

        _assert_located_extract_item(items=raised.value.to_error_report().validation_errors or [], bundle_path=bundle_path)
