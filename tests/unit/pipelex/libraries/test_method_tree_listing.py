import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from mthds.method_tree.models import MethodTree, TreeLimits
from mthds.package.dependency_resolver import ResolvedDependency
from mthds.package.manifest.schema import MethodsManifest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_library_manager, scoped_current_library
from pipelex.libraries import method_requirements, method_tree_listing
from pipelex.libraries.exceptions import MethodTreeChangedError, MethodTreeLoadError
from pipelex.libraries.library_manager import LibraryManager
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.libraries.method_trees import ensure_bundle_text_as_listed, list_local_method_tree, listing_identity, read_tree_file_as_listed
from pipelex.methods.package_reason import MethodPackageReason

_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/listing"\nversion = "1.0.0"\ndescription = "A listed package"\n'
_BUNDLE = "domain = 'listing_tests'\n"
_PACKAGE_ADDRESS = "github.com/pipelex-tests/listing-dependency"
# How long a thread waits for another before the test gives up on it, and how long a judgement holds the tree while a
# second ask arrives: a second judgement arriving in that time is a second call the listing should have prevented.
_WAIT_SECONDS = 5.0
_HOLD_SECONDS = 0.3


def _touch(*, directory: Path, tree_path: str, content: str = _BUNDLE) -> Path:
    file_path = directory / tree_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


def _refusal_params(*, error: MethodTreeLoadError) -> dict[str, object]:
    problem = error.to_problem(view=ProblemView.CALLER)
    return problem.params.as_wire() if problem.params is not None else {}


class TestMethodTreeListing:
    def test_a_bundle_file_named_alone_is_rooted_at_the_manifest_above_it_else_alone(self, tmp_path: Path) -> None:
        """Named alone, a bundle reads the files of the method a METHODS.toml above it roots, and with none only itself."""
        lone = _touch(directory=tmp_path, tree_path="loose/lone.mthds")
        _touch(directory=tmp_path, tree_path="loose/notes.md")
        _touch(directory=tmp_path, tree_path="method/METHODS.toml", content=_MANIFEST)
        rooted = _touch(directory=tmp_path, tree_path="method/bundles/main.mthds")
        tree_listing = MethodTreeListing()

        lone_bundle = tree_listing.lone_file_bundle(bundle_file=lone)
        rooted_bundle = tree_listing.lone_file_bundle(bundle_file=rooted)

        assert lone_bundle.tree.is_one_file
        assert lone_bundle.tree.tree_paths == ["lone.mthds"]
        assert not rooted_bundle.tree.is_one_file
        assert rooted_bundle.tree_path == "bundles/main.mthds"
        assert rooted_bundle.tree.tree_paths == ["METHODS.toml", "bundles/main.mthds"]

    @pytest.mark.parametrize("with_manifest", [True, False])
    @pytest.mark.parametrize("real_file_first", [True, False])
    def test_a_symbolic_link_named_alone_is_refused_whichever_the_run_listed_first(
        self, tmp_path: Path, with_manifest: bool, real_file_first: bool
    ) -> None:
        """The link is refused as the lister refuses it, even once the run listed the file it points to, and the file still lists."""
        if with_manifest:
            _touch(directory=tmp_path, tree_path="method/METHODS.toml", content=_MANIFEST)
        real_file = _touch(directory=tmp_path, tree_path="method/main.mthds")
        link = tmp_path / "elsewhere" / "link.mthds"
        link.parent.mkdir()
        link.symlink_to(real_file)
        with pytest.raises(MethodTreeLoadError) as lister_refusal:
            list_local_method_tree(handed_over=link)
        tree_listing = MethodTreeListing()

        if real_file_first:
            tree_listing.lone_file_bundle(bundle_file=real_file)
        with pytest.raises(MethodTreeLoadError) as listing_refusal:
            tree_listing.method_tree(handed_over=link)
        real_bundle = tree_listing.lone_file_bundle(bundle_file=real_file)

        assert listing_refusal.value.message == lister_refusal.value.message
        assert _refusal_params(error=listing_refusal.value) == _refusal_params(error=lister_refusal.value)
        assert real_bundle.tree_path == "main.mthds"

    @pytest.mark.parametrize("real_directory_first", [True, False])
    def test_a_symbolic_link_naming_a_directory_is_followed_as_the_lister_follows_it(
        self, mocker: MockerFixture, tmp_path: Path, real_directory_first: bool
    ) -> None:
        """A directory and a link naming it are one tree, listed once, whichever the run asks for first."""
        real_directory = tmp_path / "method"
        _touch(directory=real_directory, tree_path="main.mthds")
        link = tmp_path / "linked-method"
        link.symlink_to(real_directory, target_is_directory=True)
        expected = list_local_method_tree(handed_over=link)
        lister = mocker.spy(method_tree_listing, "list_local_method_tree")
        tree_listing = MethodTreeListing()

        first, second = (real_directory, link) if real_directory_first else (link, real_directory)
        first_tree = tree_listing.method_tree(handed_over=first)
        second_tree = tree_listing.method_tree(handed_over=second)

        assert second_tree is first_tree
        assert lister.call_count == 1
        assert listing_identity(tree=first_tree) == listing_identity(tree=expected)

    @pytest.mark.parametrize("bundle_file_first", [True, False])
    def test_a_bundle_file_named_alone_inside_a_library_directory_shares_the_directory_s_listing(
        self, mocker: MockerFixture, tmp_path: Path, bundle_file_first: bool
    ) -> None:
        """`run bundle dir/bundles/main.mthds -L dir` lists the tree rooted at `dir` once, for the file and for the directory."""
        library_dir = tmp_path / "library"
        _touch(directory=library_dir, tree_path="METHODS.toml", content=_MANIFEST)
        bundle_file = _touch(directory=library_dir, tree_path="bundles/main.mthds")
        expected = list_local_method_tree(handed_over=bundle_file)
        lone_file_lister = mocker.spy(method_tree_listing, "list_local_method_tree")
        library_dir_lister = mocker.spy(method_tree_listing, "list_library_dir_tree")
        tree_listing = MethodTreeListing()

        if bundle_file_first:
            tree_bundle = tree_listing.lone_file_bundle(bundle_file=bundle_file)
            library_trees = tree_listing.library_trees(library_dir=library_dir)
        else:
            library_trees = tree_listing.library_trees(library_dir=library_dir)
            tree_bundle = tree_listing.lone_file_bundle(bundle_file=bundle_file)

        assert lone_file_lister.call_count + library_dir_lister.call_count == 1
        assert tree_bundle.tree_path == "bundles/main.mthds"
        assert tree_bundle.tree.entry == expected.entry
        assert listing_identity(tree=tree_bundle.tree) == listing_identity(tree=expected)
        assert [listing_identity(tree=tree) for tree in library_trees] == [listing_identity(tree=expected)]

    def test_concurrent_asks_of_one_tree_list_it_once_while_other_trees_list_beside_them(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Two asks of one tree wait for one listing, and a third tree lists at the same moment: the barrier needs both listings at once."""
        shared_directory = tmp_path / "shared"
        other_directory = tmp_path / "other"
        _touch(directory=shared_directory, tree_path="main.mthds")
        _touch(directory=other_directory, tree_path="main.mthds")
        list_for_real = method_tree_listing.list_local_method_tree
        both_listing = threading.Barrier(2, timeout=_WAIT_SECONDS)
        listed: list[Path] = []

        def list_beside_another(*, handed_over: Path, limits: TreeLimits | None = None) -> MethodTree:
            listed.append(handed_over)
            both_listing.wait()
            return list_for_real(handed_over=handed_over, limits=limits)

        mocker.patch.object(method_tree_listing, "list_local_method_tree", side_effect=list_beside_another)
        tree_listing = MethodTreeListing()
        assert tree_listing.limits is not None

        with ThreadPoolExecutor(max_workers=3) as pool:
            shared_asks = [pool.submit(tree_listing.method_tree, handed_over=shared_directory) for _ in range(2)]
            other_ask = pool.submit(tree_listing.method_tree, handed_over=other_directory)
            shared_trees = [ask.result(timeout=_WAIT_SECONDS * 2) for ask in shared_asks]
            other_tree = other_ask.result(timeout=_WAIT_SECONDS * 2)

        assert shared_trees[0] is shared_trees[1]
        assert other_tree.directory != shared_trees[0].directory
        assert sorted(listed) == sorted([shared_directory, other_directory])

    def test_concurrent_judgements_of_one_tree_judge_it_once_per_environment(self, tmp_path: Path) -> None:
        """A second judgement waits for the first and takes its verdict; another environment, or a refusal, judges again."""
        _touch(directory=tmp_path, tree_path="main.mthds")
        tree_listing = MethodTreeListing()
        tree = tree_listing.method_tree(handed_over=tmp_path)
        first_judging = threading.Event()
        second_judging = threading.Event()
        judgements: list[str] = []

        def judge() -> None:
            judgements.append("judged")
            if len(judgements) == 1:
                first_judging.set()
                second_judging.wait(timeout=_HOLD_SECONDS)
            else:
                second_judging.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(tree_listing.judge_requirements_once, tree=tree, judged_against="daytona", judge=judge)
            assert first_judging.wait(timeout=_WAIT_SECONDS)
            second = pool.submit(tree_listing.judge_requirements_once, tree=tree, judged_against="daytona", judge=judge)
            first.result(timeout=_WAIT_SECONDS)
            second.result(timeout=_WAIT_SECONDS)
        assert judgements == ["judged"]

        tree_listing.judge_requirements_once(tree=tree, judged_against="direct", judge=judge)
        tree_listing.judge_requirements_once(tree=tree, judged_against="daytona", judge=judge)
        assert judgements == ["judged", "judged"]

        def refuse() -> None:
            judgements.append("refused")
            msg = "refused"
            raise ValueError(msg)

        for _ in range(2):
            with pytest.raises(ValueError, match="refused"):
                tree_listing.judge_requirements_once(tree=tree, judged_against="elsewhere", judge=refuse)
        assert judgements == ["judged", "judged", "refused", "refused"]

    def test_a_tree_edited_after_its_listing_is_refused_as_a_load_takes_it(self, tmp_path: Path) -> None:
        """A template edited between the command's listing and the load is refused with `tree_changed`, naming the file."""
        _touch(directory=tmp_path, tree_path="main.mthds")
        template = _touch(directory=tmp_path, tree_path="templates/letter.md", content="Dear $name,\n")
        tree_listing = MethodTreeListing()
        tree_listing.method_tree(handed_over=tmp_path)

        template.write_text("Dear $name, edited\n", encoding="utf-8")
        tree_listing.method_tree(handed_over=tmp_path)
        with tree_listing.loading(), pytest.raises(MethodTreeChangedError) as exc_info:
            tree_listing.method_tree(handed_over=tmp_path)

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_PACKAGE_INVALID
        assert _refusal_params(error=exc_info.value) == {"reason": MethodPackageReason.TREE_CHANGED, "path": "templates/letter.md"}
        assert "'templates/letter.md'" in exc_info.value.message

    def test_a_load_reads_a_tree_listed_before_it_again_once_and_a_tree_it_lists_never(self, mocker: MockerFixture, tmp_path: Path) -> None:
        listed_before = tmp_path / "listed-before"
        listed_by_the_load = tmp_path / "listed-by-the-load"
        _touch(directory=listed_before, tree_path="main.mthds")
        _touch(directory=listed_by_the_load, tree_path="main.mthds")
        tree_listing = MethodTreeListing()
        tree_listing.method_tree(handed_over=listed_before)
        read_again = mocker.spy(method_tree_listing, "ensure_tree_files_as_listed")

        with tree_listing.loading():
            tree_listing.method_tree(handed_over=listed_before)
            tree_listing.method_tree(handed_over=listed_by_the_load)
            with tree_listing.loading():
                tree_listing.method_tree(handed_over=listed_before)
                tree_listing.method_tree(handed_over=listed_by_the_load)
        with tree_listing.loading():
            tree_listing.method_tree(handed_over=listed_before)

        assert [call.kwargs["tree"].directory for call in read_again.call_args_list] == [listed_before.resolve()]

    def test_a_bundle_read_after_its_listing_is_read_as_listed(self, tmp_path: Path) -> None:
        """A reader's text of a listed bundle is the bundle's when it is the listed file's, its line endings kept or made newlines."""
        bundle_file = tmp_path / "main.mthds"
        bundle_file.write_bytes(b"domain = 'listing_tests'\r\n")
        tree_listing = MethodTreeListing()
        tree_bundle = tree_listing.lone_file_bundle(bundle_file=bundle_file)

        assert read_tree_file_as_listed(tree=tree_bundle.tree, tree_path="main.mthds") == b"domain = 'listing_tests'\r\n"
        ensure_bundle_text_as_listed(tree_bundle=tree_bundle, mthds_content="domain = 'listing_tests'\n")
        ensure_bundle_text_as_listed(tree_bundle=tree_bundle, mthds_content="domain = 'listing_tests'\r\n")
        with pytest.raises(MethodTreeChangedError):
            ensure_bundle_text_as_listed(tree_bundle=tree_bundle, mthds_content="domain = 'another'\n")

        bundle_file.write_bytes(b"domain = 'edited'\n")
        with pytest.raises(MethodTreeChangedError, match="changed since the tree was listed"):
            read_tree_file_as_listed(tree=tree_bundle.tree, tree_path="main.mthds")
        bundle_file.unlink()
        with pytest.raises(MethodTreeChangedError, match="was removed or became unreadable"):
            read_tree_file_as_listed(tree=tree_bundle.tree, tree_path="main.mthds")

    def test_a_dependency_package_is_listed_and_judged_once_per_run(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Two loads of one run reading one package list its tree once and judge its requirements once."""
        package_root = tmp_path / "package"
        package_bundle = _touch(directory=package_root, tree_path="notes.mthds", content="domain = 'listing_dependency'\n")
        _touch(directory=package_root, tree_path="helpers.py", content="VALUE = 1\n")
        _touch(directory=package_root, tree_path="requirements.txt", content="pydantic>=2\n")
        resolved_dep = ResolvedDependency(
            alias="listing_dependency",
            address=_PACKAGE_ADDRESS,
            manifest=MethodsManifest(address=_PACKAGE_ADDRESS, version="1.0.0", description="A listed dependency"),
            package_root=package_root,
            mthds_files=[package_bundle],
            exported_pipe_codes=None,
        )
        package_lister = mocker.spy(method_tree_listing, "list_package_method_tree")
        environment_resolver = mocker.spy(method_requirements, "resolve_pipe_func_package_environment")
        library_manager = get_library_manager()
        assert isinstance(library_manager, LibraryManager)
        tree_listing = MethodTreeListing()

        for _ in range(2):
            library_id, library = library_manager.open_library()
            try:
                with scoped_current_library(library_id=library_id):
                    library_manager._load_single_dependency(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                        library=library,
                        library_id=library_id,
                        resolved_dep=resolved_dep,
                        package_address=_PACKAGE_ADDRESS,
                        tree_listing=tree_listing,
                    )
            finally:
                library_manager.teardown(library_id=library_id)

        assert package_lister.call_count == 1
        assert environment_resolver.call_count == 1
