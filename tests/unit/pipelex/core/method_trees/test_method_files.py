import re

import pytest
from mthds.method_tree.digest import DIGEST_PREFIX, digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pytest_mock import MockerFixture

from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.method_trees.method_file_store import HeldFile, LocalMethodFileStore
from pipelex.core.method_trees.method_files import StoredTree, TreeListing, read_method_file, read_stored_trees, read_tree_files, read_tree_listing
from pipelex.core.method_trees.tree_bundle import MethodFileRef

_FILES = {"main.mthds": b'domain = "letters"\n', "templates/letter.html": b"<p>{{ name }}</p>\n", "logo.png": bytes(range(64))}


def _held(files: dict[str, bytes]) -> dict[str, HeldFile]:
    return {path: HeldFile.of_bytes(data=data) for path, data in files.items()}


class TestMethodFiles:
    @pytest.fixture(autouse=True)
    def _isolated_store(self, mocker: MockerFixture, store: LocalMethodFileStore) -> None:
        mocker.patch("pipelex.core.method_trees.method_files.get_method_file_store", return_value=store)

    def test_a_listing_is_checked_against_the_digest_that_names_it(self) -> None:
        listing = tree_listing(tree_files_from_contents(_FILES))

        parsed = TreeListing.parse(tree_digest=digest_of_contents(_FILES), listing=listing)

        assert parsed.files == {tree_path: sha256_hex(data) for tree_path, data in _FILES.items()}
        with pytest.raises(MethodFileUnavailableError, match="not the one its digest names"):
            TreeListing.parse(tree_digest=digest_of_contents({"other.txt": b"x"}), listing=listing)

    @pytest.mark.asyncio
    async def test_a_method_file_is_read_by_its_tree_and_tree_path(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))

        data = await read_method_file(file_ref=MethodFileRef(tree_digest=tree.digest, tree_path="templates/letter.html"), read_scope=None)

        assert data == _FILES["templates/letter.html"]

    @pytest.mark.asyncio
    async def test_a_file_the_tree_does_not_hold_is_refused_naming_it(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))

        with pytest.raises(MethodFileUnavailableError, match=re.escape("holds no file 'templates/missing.html'")):
            await read_method_file(file_ref=MethodFileRef(tree_digest=tree.digest, tree_path="templates/missing.html"), read_scope=None)

    @pytest.mark.asyncio
    async def test_bytes_the_store_serves_wrong_are_refused(self, store: LocalMethodFileStore, mocker: MockerFixture) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))
        mocker.patch.object(store, "read_blob", return_value=b"tampered")

        with pytest.raises(MethodFileUnavailableError, match="are not the file's"):
            await read_tree_files(tree_digest=tree.digest, read_scope="org/acme")

    @pytest.mark.asyncio
    async def test_the_read_scope_reaches_the_store(self, store: LocalMethodFileStore, mocker: MockerFixture) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))
        read_tree_listing_spy = mocker.spy(store, "read_tree_listing")

        listing = await read_tree_listing(tree_digest=tree.digest, read_scope="org/acme")

        assert set(listing.files) == set(_FILES)
        read_tree_listing_spy.assert_called_once_with(tree_digest=tree.digest, read_scope="org/acme")

    @pytest.mark.asyncio
    async def test_a_filter_reads_only_the_files_it_keeps(self, store: LocalMethodFileStore) -> None:
        tree = store.hold_files(holder="library", files=_held(_FILES))

        files = await read_tree_files(tree_digest=tree.digest, read_scope=None, keeps=lambda tree_path: tree_path.endswith(".png"))

        assert files == {"logo.png": _FILES["logo.png"]}

    def test_a_listing_splits_on_line_feeds_alone(self) -> None:
        """U+2028 and U+2029 may sit in a tree path, and `str.splitlines` would split a line on either."""
        files = {"notes/line\u2028separator.txt": b"a", "notes/paragraph\u2029separator.txt": b"b", "main.mthds": b"c"}
        listing = tree_listing(tree_files_from_contents(files))

        parsed = TreeListing.parse(tree_digest=digest_of_contents(files), listing=listing)

        assert parsed.files == {tree_path: sha256_hex(data) for tree_path, data in files.items()}

    def test_a_listing_whose_last_line_has_no_line_feed_is_refused(self) -> None:
        """A listing its digest names, but whose last line has lost its line feed, is not one the standard writes."""
        truncated = tree_listing(tree_files_from_contents(_FILES)).rstrip(b"\n")

        with pytest.raises(MethodFileUnavailableError, match="does not end with a line feed"):
            TreeListing.parse(tree_digest=DIGEST_PREFIX + sha256_hex(truncated), listing=truncated)

    def test_an_empty_listing_names_an_empty_tree(self) -> None:
        assert TreeListing.parse(tree_digest=digest_of_contents({}), listing=b"").files == {}

    @pytest.mark.asyncio
    async def test_the_trees_a_job_names_are_read_as_a_store_keeps_them(self, store: LocalMethodFileStore) -> None:
        """Each tree once, its listing under its digest and each distinct file once, under its hash, read under the run's read scope."""
        tree = store.hold_files(holder="library", files=_held({**_FILES, "copy/logo.png": _FILES["logo.png"]}))
        other = store.hold_files(holder="library", files=_held({"notes.txt": b"notes"}))

        stored_trees = await read_stored_trees(tree_digests=[tree.digest, other.digest], read_scope="org/acme")

        assert stored_trees == [
            StoredTree(
                tree_digest=tree.digest,
                listing=tree_listing(tree_files_from_contents({**_FILES, "copy/logo.png": _FILES["logo.png"]})),
                blobs={sha256_hex(data): data for data in _FILES.values()},
            ),
            StoredTree(
                tree_digest=other.digest,
                listing=tree_listing(tree_files_from_contents({"notes.txt": b"notes"})),
                blobs={sha256_hex(b"notes"): b"notes"},
            ),
        ]

    @pytest.mark.asyncio
    async def test_a_tree_no_library_holds_cannot_be_copied(self) -> None:
        with pytest.raises(MethodFileUnavailableError, match="holds no tree"):
            await read_stored_trees(tree_digests=[digest_of_contents({"gone.txt": b"gone"})], read_scope=None)
