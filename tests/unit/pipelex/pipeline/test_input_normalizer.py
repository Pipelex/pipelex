"""Unit tests for input_normalizer URL handling.

Regression coverage for the hosted-runner 500 (2026-06-11): a DocumentContent
with a blank url resolved as local path '', `Path('')` became `'.'`, and the
uncaught `IsADirectoryError` escaped as an InternalServerError. Both the blank
url and any unreadable local path must surface as the INPUT-domain
`PipelineInputContentError` (→ 422 at the API layer), never a sanitized 500.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.exceptions import PipelineInputContentError
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
        return_value=mocker.Mock(pipelex=mocker.Mock(storage_config=mocker.Mock(is_upload_local_content_enabled=True))),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerUrlGuards:
    @pytest.mark.parametrize("blank_url", ["", "   "])
    async def test_blank_url_raises_input_error(self, mocker: MockerFixture, blank_url: str) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="blank url"):
            await normalize_data_urls_to_storage(_memory_with_document(blank_url))

    async def test_directory_path_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A local path that IS a directory must be an input error, not an
        escaped IsADirectoryError (the '.'-as-url production failure mode).
        """
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await normalize_data_urls_to_storage(_memory_with_document(str(tmp_path)))

    async def test_missing_file_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await normalize_data_urls_to_storage(_memory_with_document(str(tmp_path / "nope.pdf")))
