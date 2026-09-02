"""Unit tests for input_normalizer URL handling.

Regression coverage for the hosted-runner 500 (2026-06-11): a DocumentContent
with a blank url resolved as local path '', `Path('')` became `'.'`, and the
uncaught `IsADirectoryError` escaped as an InternalServerError. Both the blank
url and any unreadable local path must surface as the INPUT-domain
`PipelineInputContentError` (→ 422 at the API layer), never a sanitized 500.

The family is split on what its message may disclose: the blank-url arm
(`PipelineInputUrlMissingError`) names only the accepted schemes and is
caller-facing copy, while the unreadable-path arm names the resolved path and
the OSError subclass and must stay redacted under STRICT disclosure.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.exceptions import PipelineInputContentError, PipelineInputUrlMissingError
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def _memory_with_document(url: str) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DOCUMENT),
        content=DocumentContent(url=url),
        name="document",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _patch_storage_and_config(mocker: MockerFixture) -> None:
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_storage_provider",
        return_value=mocker.Mock(spec=StorageProviderAbstract),
    )
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=True))),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerUrlGuards:
    @pytest.mark.parametrize("blank_url", ["", "   "])
    async def test_blank_url_raises_input_error(self, mocker: MockerFixture, blank_url: str) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputUrlMissingError, match="blank url"):
            await normalize_data_urls_to_storage(_memory_with_document(blank_url), storage_scope="test/scope")

    async def test_blank_url_message_survives_strict_disclosure(self, mocker: MockerFixture) -> None:
        """The blank-url message names only the accepted schemes, so STRICT keeps it.

        Under the placeholder a caller who simply forgot a url is told "internal
        error" and has nothing to act on.
        """
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputUrlMissingError) as exc_info:
            await normalize_data_urls_to_storage(_memory_with_document(""), storage_scope="test/scope")

        strict = exc_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert "blank url" in strict["message"]

    async def test_unreadable_path_message_is_redacted_under_strict_disclosure(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The unreadable-path message must NOT reach a caller under STRICT disclosure.

        It names the resolved path and the OSError subclass that rejected it. Letting
        those through would answer "does this server-side path exist, and may the runner
        read it?" — ``PermissionError`` on an existing path reads differently from
        ``FileNotFoundError`` on one that does not — for any authenticated caller of a
        deployment that leaves ``is_upload_local_content_enabled`` on.
        """
        _patch_storage_and_config(mocker)
        missing_path = tmp_path / "nope.pdf"

        with pytest.raises(PipelineInputContentError) as exc_info:
            await normalize_data_urls_to_storage(_memory_with_document(str(missing_path)), storage_scope="test/scope")

        report = exc_info.value.to_error_report()
        assert str(missing_path) in report.message, "precondition: the raw message carries the path"
        strict = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict["message"] == INTERNAL_ERROR_PLACEHOLDER
        assert str(missing_path) not in str(strict)
        assert "FileNotFoundError" not in str(strict)

    async def test_directory_path_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A local path that IS a directory must be an input error, not an
        escaped IsADirectoryError (the '.'-as-url production failure mode).
        """
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await normalize_data_urls_to_storage(_memory_with_document(str(tmp_path)), storage_scope="test/scope")

    async def test_missing_file_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await normalize_data_urls_to_storage(_memory_with_document(str(tmp_path / "nope.pdf")), storage_scope="test/scope")
