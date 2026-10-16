import asyncio
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from mthds.method_tree.lister import list_method_tree
from pytest_mock import MockerFixture

from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES, HeldFile, LocalMethodFileStore, tree_of_held_files
from pipelex.runtime_hub import get_method_file_store

_FILES = {"main.mthds": b'domain = "letters"\n', "templates/letter.html": b"<p>{{ name }}</p>\n", "logo.png": bytes(range(64))}


def _held(files: dict[str, bytes]) -> dict[str, HeldFile]:
    return {path: HeldFile.of_bytes(data=data) for path, data in files.items()}


class TestLocalMethodFileStore:
    def test_a_tree_of_held_files_has_the_digest_of_the_same_files_anywhere(self) -> None:
        tree = tree_of_held_files(files=_held(_FILES))

        assert tree.digest == digest_of_contents(_FILES)
        assert tree.directory is None
        assert tree.tree_paths == sorted(_FILES)

    @pytest.mark.asyncio
    async def test_a_held_tree_serves_its_listing_and_its_files(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))

        listing = await store.read_tree_listing(tree_digest=tree.digest, read_scope=None)

        assert listing == tree_listing(tree_files_from_contents(_FILES))
        assert await store.read_blob(sha256=sha256_hex(_FILES["logo.png"]), read_scope=None) == _FILES["logo.png"]
        assert store.read_held_file(tree_digest=tree.digest, tree_path="templates/letter.html") == _FILES["templates/letter.html"]

    @pytest.mark.asyncio
    async def test_a_tree_is_served_until_its_last_holder_releases_it(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="first", files=_held(_FILES))
        store.hold_files(holder="second", files=_held(_FILES))

        store.release(holder="first")
        assert store.held_tree(tree_digest=tree.digest) is not None

        store.release(holder="second")
        assert store.held_tree(tree_digest=tree.digest) is None
        assert await store.read_tree_listing(tree_digest=tree.digest, read_scope=None) is None
        assert await store.read_blob(sha256=sha256_hex(_FILES["logo.png"]), read_scope=None) is None

    def test_a_tree_listed_from_a_directory_is_read_from_it(self, store: LocalMethodFileStore, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        for tree_path, data in _FILES.items():
            (tmp_path / tree_path).write_bytes(data)
        tree = list_method_tree(tmp_path)

        store.hold_tree(holder="library", tree=tree)

        assert store.read_held_file(tree_digest=tree.digest, tree_path="logo.png") == _FILES["logo.png"]

    def test_a_file_edited_after_its_tree_was_listed_is_not_served(self, store: LocalMethodFileStore, tmp_path: Path) -> None:
        (tmp_path / "templates").mkdir()
        for tree_path, data in _FILES.items():
            (tmp_path / tree_path).write_bytes(data)
        tree = list_method_tree(tmp_path)
        store.hold_tree(holder="library", tree=tree)

        (tmp_path / "templates" / "letter.html").write_bytes(b"<p>edited</p>\n")

        assert store.read_held_file(tree_digest=tree.digest, tree_path="templates/letter.html") is None

    def test_a_tree_assembled_in_memory_is_held_with_its_files(self, store: LocalMethodFileStore) -> None:
        with pytest.raises(ValueError, match="hold_files"):
            store.hold_tree(holder="library", tree=tree_of_held_files(files=_held(_FILES)))

    def test_the_hub_reads_through_the_local_store_unless_a_plugin_claims_the_slot(self) -> None:
        assert get_method_file_store() is LOCAL_METHOD_FILES

    def test_a_tree_two_libraries_hold_is_served_from_whichever_source_still_holds_its_bytes(
        self, store: LocalMethodFileStore, tmp_path: Path
    ) -> None:
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        for directory in (first_dir, second_dir):
            (directory / "templates").mkdir(parents=True)
            for tree_path, data in _FILES.items():
                (directory / tree_path).write_bytes(data)
        first_tree = list_method_tree(first_dir)
        second_tree = list_method_tree(second_dir)
        assert first_tree.digest == second_tree.digest
        store.hold_tree(holder="first", tree=first_tree)
        store.hold_tree(holder="second", tree=second_tree)

        (first_dir / "logo.png").unlink()

        assert store.read_held_file(tree_digest=first_tree.digest, tree_path="logo.png") == _FILES["logo.png"]
        store.release(holder="second")
        assert store.read_held_file(tree_digest=first_tree.digest, tree_path="logo.png") is None
        assert store.read_held_file(tree_digest=first_tree.digest, tree_path="main.mthds") == _FILES["main.mthds"]

    def test_a_tree_held_again_by_its_holder_keeps_its_first_sources(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))

        assert store.holds(holder="library", tree_digest=tree.digest)
        store.hold_files(holder="library", files=_held(_FILES))

        assert len(store.held_files_with_hash(sha256=sha256_hex(_FILES["logo.png"]))) == 1
        assert not store.holds(holder="other", tree_digest=tree.digest)

    @pytest.mark.asyncio
    async def test_the_index_by_hash_follows_holds_and_releases(self, store: LocalMethodFileStore) -> None:
        logo_sha256 = sha256_hex(_FILES["logo.png"])
        store.hold_files(holder="first", files=_held(_FILES))
        store.hold_files(holder="second", files=_held({"assets/logo.png": _FILES["logo.png"]}))
        assert len(store.held_files_with_hash(sha256=logo_sha256)) == 2

        store.release(holder="first")
        assert len(store.held_files_with_hash(sha256=logo_sha256)) == 1
        assert store.held_files_with_hash(sha256=sha256_hex(_FILES["main.mthds"])) == []
        assert await store.read_blob(sha256=logo_sha256, read_scope=None) == _FILES["logo.png"]

        store.hold_files(holder="third", files=_held(_FILES))
        store.release_all()
        assert store.held_files_with_hash(sha256=logo_sha256) == []
        assert await store.read_blob(sha256=logo_sha256, read_scope=None) is None

    @pytest.mark.asyncio
    async def test_a_blob_on_disk_is_read_off_the_event_loop_and_checked_against_its_hash(
        self, store: LocalMethodFileStore, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        (tmp_path / "templates").mkdir()
        for tree_path, data in _FILES.items():
            (tmp_path / tree_path).write_bytes(data)
        store.hold_tree(holder="library", tree=list_method_tree(tmp_path))
        to_thread_spy = mocker.spy(asyncio, "to_thread")

        assert await store.read_blob(sha256=sha256_hex(_FILES["logo.png"]), read_scope=None) == _FILES["logo.png"]
        to_thread_spy.assert_called_once()

        (tmp_path / "logo.png").write_bytes(b"edited")
        assert await store.read_blob(sha256=sha256_hex(_FILES["logo.png"]), read_scope=None) is None
