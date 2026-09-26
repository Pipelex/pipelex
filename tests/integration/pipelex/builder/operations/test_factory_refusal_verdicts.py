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
from pytest_mock import MockerFixture

from pipelex.base_exceptions import DisclosureMode, ErrorDomain, PipelexError, ValidationErrorCategory, ValidationErrorItem
from pipelex.builder.operations.validate_ops import validate_all, validate_pipe
from pipelex.core.pipes.exceptions import PipeLoadRefusalError
from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.exceptions import LibraryError
from pipelex.libraries.pipe.exceptions import EntryPipeAmbiguousError
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

_SEQUENCE_OUTPUT_MISMATCH_BUNDLE = f"""
domain      = "{_DOMAIN}"
description = "Read the pages of a tide almanac"

[pipe.summarize_almanac]
type        = "PipeSequence"
description = "Summarize the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Text[]"
steps       = [{{ pipe = "write_summary", result = "summary" }}]

[pipe.write_summary]
type        = "PipeLLM"
description = "Write the summary of the tide almanac"
inputs      = {{ almanac_text = "Text" }}
output      = "Text"
prompt      = "Summarize this tide almanac: $almanac_text"
"""

_INHERITED_SYSTEM_PROMPT_BUNDLE = """
domain        = "almanac_notes"
description   = "Write notes about a tide almanac"
system_prompt = "You write for {% if %} harbour users."

[pipe.write_note]
type        = "PipeLLM"
description = "Write a note about the tide almanac"
inputs      = { almanac_text = "Text" }
output      = "Text"
prompt      = "Write a note about this tide almanac: $almanac_text"
"""


def _write_named_pipe_bundle(*, directory: Path, domain_code: str) -> None:
    content = f"""
domain      = "{domain_code}"
description = "Write notes for the harbour board"

[pipe.write_note]
type        = "PipeLLM"
description = "Write a note for the harbour board"
inputs      = {{ tide_times = "Text" }}
output      = "Text"
prompt      = "Write a note from these tide times: $tide_times"
"""
    (directory / f"{domain_code}.mthds").write_text(content, encoding="utf-8")


_NEXT_STEP = "Declare this input as an Image or a Document, or as a concept that refines one of them."

_FACTORY_REFUSAL_CLASSES: list[type[PipelexError]] = [
    PipeLLMFactoryError,
    PipeComposeFactoryError,
    PipeExtractFactoryError,
    PipeConditionFactoryError,
    PipeParallelFactoryError,
]


def _write_bundle(*, directory: Path, content: str = _TEXT_INPUT_EXTRACT_BUNDLE) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(content, encoding="utf-8")
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

    async def test_validate_ops_validate_all_locates_a_wiring_refusal_on_its_file(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_SEQUENCE_OUTPUT_MISMATCH_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_all(library_dirs=[tmp_path])

        (item,) = raised.value.to_error_report().validation_errors or []
        assert item.pipe_code == "summarize_almanac"
        assert item.source == str(bundle_path)

    async def test_validate_ops_validate_all_lets_a_teardown_fault_propagate(self, tmp_path: Path, mocker: MockerFixture) -> None:
        _write_bundle(directory=tmp_path, content=_SEQUENCE_OUTPUT_MISMATCH_BUNDLE.replace('output      = "Text[]"', 'output      = "Text"'))
        library_manager = get_library_manager()
        real_teardown = library_manager.teardown
        fault = LibraryError("the library could not be torn down")

        def _teardown_then_fail(*, library_id: str) -> None:
            real_teardown(library_id=library_id)
            raise fault

        mocker.patch.object(library_manager, "teardown", side_effect=_teardown_then_fail)

        with pytest.raises(LibraryError) as raised:
            await validate_all(library_dirs=[tmp_path])

        assert raised.value is fault

    async def test_validate_ops_validate_pipe_keeps_an_ambiguous_code_out_of_the_verdict(self, tmp_path: Path) -> None:
        _write_named_pipe_bundle(directory=tmp_path, domain_code="harbour_notes")
        _write_named_pipe_bundle(directory=tmp_path, domain_code="quay_notes")

        with pytest.raises(EntryPipeAmbiguousError):
            await validate_pipe("write_note", library_dirs=[tmp_path])

    async def test_an_inherited_system_prompt_refusal_names_the_domain(self, tmp_path: Path) -> None:
        bundle_path = _write_bundle(directory=tmp_path, content=_INHERITED_SYSTEM_PROMPT_BUNDLE)

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        (item,) = raised.value.to_error_report().validation_errors or []
        assert item.pipe_code == "write_note"
        assert item.source == str(bundle_path)
        assert "system prompt of domain 'almanac_notes', which it inherits, for pipe 'write_note' in domain" in item.message
        assert "{% if %}" in item.message
