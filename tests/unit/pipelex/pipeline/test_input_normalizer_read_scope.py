"""The input normalization authorizes every url against the run's read scope before reading or linking it.

On a scoped run a local path is refused, naming the input, instead of being uploaded or kept for the
prompt preparation to read later, and that holds whether local uploads are enabled or not. A storage
reference outside the scope is refused instead of being signed, since a signed link is a read by
whoever holds it. An unscoped run normalizes as it always did.
"""

from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError

READ_SCOPE = "org_abc"
STORAGE_SCOPE = "org_abc/mt_1/run_1"


def _memory_with_image(url: str) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
        content=ImageContent(url=url),
        name="photo",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _memory_with_image_list(urls: list[str]) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
        content=ListContent[ImageContent](items=[ImageContent(url=url) for url in urls]),
        name="album",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _patch_storage_and_config(mocker: MockerFixture, *, is_upload_local_content_enabled: bool) -> Any:
    storage = mocker.Mock(spec=StorageProviderAbstract)
    storage.public_url = mocker.AsyncMock(return_value="https://signed.example/link")
    storage.store = mocker.AsyncMock(return_value="pipelex-storage://org_abc/mt_1/run_1/assets/x.png")
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage)
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=is_upload_local_content_enabled))),
    )
    return storage


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerReadScope:
    @pytest.mark.parametrize("is_upload_local_content_enabled", [True, False])
    async def test_a_scoped_run_refuses_a_local_path_naming_the_input(
        self, mocker: MockerFixture, tmp_path: Path, is_upload_local_content_enabled: bool
    ) -> None:
        storage = _patch_storage_and_config(mocker, is_upload_local_content_enabled=is_upload_local_content_enabled)
        local_file = tmp_path / "photo.png"
        local_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        with pytest.raises(UriReadRefusedError) as exc_info:
            await normalize_data_urls_to_storage(_memory_with_image(str(local_file)), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE)

        assert exc_info.value.reason == UriReadRefusalReason.LOCAL_PATH
        assert "input 'photo'" in str(exc_info.value)
        assert str(local_file) not in str(exc_info.value)
        storage.store.assert_not_called()

    async def test_a_scoped_run_refuses_a_file_uri(self, mocker: MockerFixture) -> None:
        _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)
        with pytest.raises(UriReadRefusedError):
            await normalize_data_urls_to_storage(_memory_with_image("file:///etc/passwd"), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE)

    async def test_a_scoped_run_refuses_to_sign_a_foreign_storage_reference(self, mocker: MockerFixture) -> None:
        storage = _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)

        with pytest.raises(UriReadRefusedError) as exc_info:
            await normalize_data_urls_to_storage(
                _memory_with_image("pipelex-storage://org_other/assets/secret.png"), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE
            )

        assert exc_info.value.reason == UriReadRefusalReason.FOREIGN_STORAGE_KEY
        storage.public_url.assert_not_called()

    async def test_a_foreign_reference_inside_a_list_is_refused_too(self, mocker: MockerFixture) -> None:
        _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)
        with pytest.raises(UriReadRefusedError) as exc_info:
            await normalize_data_urls_to_storage(
                _memory_with_image_list(["pipelex-storage://org_abc/assets/ok.png", "pipelex-storage://org_other/assets/secret.png"]),
                storage_scope=STORAGE_SCOPE,
                read_scope=READ_SCOPE,
            )
        assert "input 'album'" in str(exc_info.value)

    async def test_a_scoped_run_signs_an_in_scope_reference(self, mocker: MockerFixture) -> None:
        storage = _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)

        working_memory = await normalize_data_urls_to_storage(
            _memory_with_image("pipelex-storage://org_abc/assets/photo.png"), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE
        )

        storage.public_url.assert_awaited_once_with(uri="pipelex-storage://org_abc/assets/photo.png")
        image_content = working_memory.get_stuff_as_image(name="photo")
        assert image_content.public_url == "https://signed.example/link"

    async def test_a_scoped_run_keeps_a_data_url_and_an_https_url(self, mocker: MockerFixture) -> None:
        _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)
        await normalize_data_urls_to_storage(
            _memory_with_image("data:image/png;base64,iVBORw0KGgo="), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE
        )
        await normalize_data_urls_to_storage(_memory_with_image("https://example.com/photo.png"), storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE)

    async def test_an_unscoped_run_uploads_a_local_path_as_before(self, mocker: MockerFixture, tmp_path: Path) -> None:
        storage = _patch_storage_and_config(mocker, is_upload_local_content_enabled=True)
        local_file = tmp_path / "photo.png"
        local_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        await normalize_data_urls_to_storage(_memory_with_image(str(local_file)), storage_scope="run_1", read_scope=None)

        storage.store.assert_awaited_once()
