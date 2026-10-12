import base64
import hashlib

import pytest
from pydantic import ValidationError

from pipelex.core.bundle_resources.bundle_resource import (
    BundleResource,
    canonical_resource_path,
    canonical_resource_path_or_none,
    make_bundle_resources,
)
from pipelex.core.bundle_resources.exceptions import BundleResourceError, BundleResourcePathError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


class TestCanonicalResourcePath:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("invoice.docx", "invoice.docx"),
            ("./invoice.docx", "invoice.docx"),
            ("templates//invoice.docx", "templates/invoice.docx"),
            ("templates/./invoice.docx", "templates/invoice.docx"),
            ("templates/invoice.docx/", "templates/invoice.docx"),
        ],
    )
    def test_a_relative_path_inside_the_bundle_has_one_spelling(self, path: str, expected: str) -> None:
        """`.` segments and repeated slashes collapse, so two spellings of one file are one key."""
        assert canonical_resource_path(path=path) == expected
        assert canonical_resource_path_or_none(path=path) == expected

    @pytest.mark.parametrize(
        ("path", "reason"),
        [
            ("", "empty"),
            ("   ", "empty"),
            (".", "names no file"),
            ("/etc/invoice.docx", "absolute"),
            ("../invoice.docx", "'..' segment"),
            ("templates/../../invoice.docx", "'..' segment"),
            ("templates\\invoice.docx", "backslash"),
            ("C:invoice.docx", "colon"),
            ("invoice\x00.docx", "NUL"),
        ],
    )
    def test_a_path_that_cannot_name_a_file_inside_the_bundle_is_refused(self, path: str, reason: str) -> None:
        """The message says why, and the lenient form answers None."""
        with pytest.raises(BundleResourcePathError) as exc_info:
            canonical_resource_path(path=path)
        assert reason in exc_info.value.message
        assert canonical_resource_path_or_none(path=path) is None


class TestBundleResource:
    def test_an_inline_resource_carries_its_bytes_and_their_digest(self) -> None:
        resource = BundleResource.make_inline(content=b"docx bytes")

        assert resource.is_inline
        assert resource.size == len(b"docx bytes")
        assert resource.sha256 == hashlib.sha256(b"docx bytes").hexdigest()
        assert resource.content_b64 == base64.b64encode(b"docx bytes").decode("ascii")
        assert resource.inline_bytes() == b"docx bytes"

    def test_a_resource_round_trips_through_json(self) -> None:
        """A crate carries its resources as JSON, so the bytes travel base64-encoded."""
        resource = BundleResource.make_inline(content=bytes(range(256)))

        assert BundleResource.model_validate_json(resource.model_dump_json()) == resource

    @pytest.mark.parametrize(
        "fields",
        [
            {"sha256": "abc", "size": 1},
            {"sha256": "abc", "size": 1, "content_b64": "eA==", "uri": "pipelex-storage://run/assets/bundle/abc/x.docx"},
            {"sha256": "abc", "size": 1, "uri": "https://example.com/x.docx"},
        ],
        ids=["neither", "both", "not_a_storage_uri"],
    )
    def test_a_resource_carries_its_bytes_one_way(self, fields: dict[str, object]) -> None:
        """Inline or by a pipelex-storage reference, exactly one of the two."""
        with pytest.raises(ValidationError):
            BundleResource.model_validate(fields)

    @pytest.mark.asyncio
    async def test_a_stored_resource_is_read_back_and_checked_against_its_digest(self) -> None:
        storage_provider = InMemoryStorageProvider()
        resource = BundleResource.make_inline(content=b"docx bytes")
        uri = await storage_provider.store(b"docx bytes", key="run/assets/bundle/digest/invoice.docx")
        stored = resource.stored_at(uri=uri)

        assert not stored.is_inline
        assert await stored.read_bytes(storage_provider=storage_provider) == b"docx bytes"
        with pytest.raises(BundleResourceError):
            stored.inline_bytes()

    @pytest.mark.asyncio
    async def test_stored_bytes_that_changed_are_refused(self) -> None:
        storage_provider = InMemoryStorageProvider()
        uri = await storage_provider.store(b"other bytes", key="run/assets/bundle/digest/invoice.docx")
        stored = BundleResource.make_inline(content=b"docx bytes").stored_at(uri=uri)

        with pytest.raises(BundleResourceError, match="no longer matches"):
            await stored.read_bytes(storage_provider=storage_provider)


class TestMakeBundleResources:
    def test_files_are_keyed_by_their_canonical_path(self) -> None:
        resources = make_bundle_resources(files={"./invoice.docx": b"docx", "templates/report.html": b"<h1></h1>"})

        assert set(resources) == {"invoice.docx", "templates/report.html"}
        assert resources["invoice.docx"].inline_bytes() == b"docx"

    def test_two_spellings_of_one_file_are_refused(self) -> None:
        with pytest.raises(BundleResourcePathError, match="name the same file"):
            make_bundle_resources(files={"invoice.docx": b"a", "./invoice.docx": b"b"})
