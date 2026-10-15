from pathlib import Path

import pytest
from mthds.method_tree.models import TreeLimits
from pytest_mock import MockerFixture

from pipelex.libraries.exceptions import MethodTreeLoadError
from pipelex.libraries.method_trees import LIMITS_ADVICE, list_library_bundle_files, tree_bundle_of_lone_file

_MANIFEST = '[package]\naddress = "github.com/pipelex-tests/nested"\nversion = "1.0.0"\ndescription = "A nested package"\n'


def _touch(*, directory: Path, tree_path: str, content: str = "domain = 'tree_tests'\n") -> Path:
    file_path = directory / tree_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestMethodTrees:
    def test_a_library_directory_lists_only_the_bundles_its_tree_holds(self, tmp_path: Path) -> None:
        """A bundle the membership rule keeps out, gitignored, hidden or in a run's output folder, is never loaded."""
        _touch(directory=tmp_path, tree_path="method/main.mthds")
        _touch(directory=tmp_path, tree_path="method/draft.mthds")
        _touch(directory=tmp_path, tree_path="method/.gitignore", content="draft.mthds\n")
        _touch(directory=tmp_path, tree_path=".archive/old.mthds")
        _touch(directory=tmp_path, tree_path="results/summarize_output_01/copy.mthds")
        _touch(directory=tmp_path, tree_path="results/summarize_output_01/.gitignore", content="*\n")

        bundle_files = list_library_bundle_files(library_dirs=[tmp_path])

        assert [bundle_file.tree_bundle.tree_path for bundle_file in bundle_files] == ["method/main.mthds"]
        assert bundle_files[0].path == tmp_path / "method" / "main.mthds"

    def test_a_nested_package_or_repository_loads_as_a_tree_of_its_own(self, tmp_path: Path) -> None:
        """A package or repository below a library directory is no part of its tree, yet its methods load, each reading its own files."""
        _touch(directory=tmp_path, tree_path="top.mthds")
        _touch(directory=tmp_path, tree_path="packages/invoicing/METHODS.toml", content=_MANIFEST)
        _touch(directory=tmp_path, tree_path="packages/invoicing/invoice.mthds")
        _touch(directory=tmp_path, tree_path="checkouts/reports/report.mthds")
        (tmp_path / "checkouts" / "reports" / ".git").mkdir()

        bundle_files = list_library_bundle_files(library_dirs=[tmp_path])

        by_location = {bundle_file.path: bundle_file.tree_bundle for bundle_file in bundle_files}
        assert set(by_location) == {
            tmp_path / "top.mthds",
            tmp_path / "packages" / "invoicing" / "invoice.mthds",
            tmp_path / "checkouts" / "reports" / "report.mthds",
        }
        invoice = by_location[tmp_path / "packages" / "invoicing" / "invoice.mthds"]
        assert invoice.tree_path == "invoice.mthds"
        assert invoice.tree.directory == (tmp_path / "packages" / "invoicing").resolve()
        report = by_location[tmp_path / "checkouts" / "reports" / "report.mthds"]
        assert report.tree.directory == (tmp_path / "checkouts" / "reports").resolve()
        assert by_location[tmp_path / "top.mthds"].tree.tree_paths == ["top.mthds"]

    def test_each_bundle_is_listed_once_as_a_member_of_the_first_tree_holding_it(self, tmp_path: Path) -> None:
        _touch(directory=tmp_path, tree_path="a.mthds")
        _touch(directory=tmp_path, tree_path="sub/b.mthds")

        bundle_files = list_library_bundle_files(library_dirs=[tmp_path, tmp_path / "sub"])

        assert [bundle_file.tree_bundle.tree_path for bundle_file in bundle_files] == ["a.mthds", "sub/b.mthds"]

    def test_a_relative_library_directory_names_its_files_relatively(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _touch(directory=tmp_path, tree_path="lib/a.mthds")
        monkeypatch.chdir(tmp_path)

        (bundle_file,) = list_library_bundle_files(library_dirs=[Path("lib")])

        assert bundle_file.path == Path("lib") / "a.mthds"

    @pytest.mark.parametrize("contents", [{}, {".hidden.mthds": "x"}], ids=["missing", "empty_tree"])
    def test_a_directory_holding_no_tree_file_holds_no_bundle(self, tmp_path: Path, contents: dict[str, str]) -> None:
        library_dir = tmp_path / "library"
        for tree_path, content in contents.items():
            _touch(directory=library_dir, tree_path=tree_path, content=content)

        assert list_library_bundle_files(library_dirs=[library_dir]) == []

    def test_a_tree_past_this_machine_s_limits_is_refused_before_it_is_read(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.libraries.method_trees.local_tree_limits", return_value=TreeLimits(max_files=1))
        _touch(directory=tmp_path, tree_path="a.mthds")
        _touch(directory=tmp_path, tree_path="b.mthds")

        with pytest.raises(MethodTreeLoadError) as exc_info:
            list_library_bundle_files(library_dirs=[tmp_path])

        assert exc_info.value.message.endswith(LIMITS_ADVICE)

    def test_a_bundle_file_named_alone_is_rooted_at_the_manifest_above_it_else_alone(self, tmp_path: Path) -> None:
        """Named alone, a bundle reads the files of the method a METHODS.toml above it roots, and with none only itself."""
        lone = _touch(directory=tmp_path, tree_path="loose/lone.mthds")
        _touch(directory=tmp_path, tree_path="loose/notes.md")
        _touch(directory=tmp_path, tree_path="method/METHODS.toml", content=_MANIFEST)
        rooted = _touch(directory=tmp_path, tree_path="method/bundles/main.mthds")

        lone_bundle = tree_bundle_of_lone_file(bundle_file=lone)
        rooted_bundle = tree_bundle_of_lone_file(bundle_file=rooted)

        assert lone_bundle.tree.is_one_file
        assert lone_bundle.tree.tree_paths == ["lone.mthds"]
        assert not rooted_bundle.tree.is_one_file
        assert rooted_bundle.tree_path == "bundles/main.mthds"
        assert rooted_bundle.tree.tree_paths == ["METHODS.toml", "bundles/main.mthds"]
