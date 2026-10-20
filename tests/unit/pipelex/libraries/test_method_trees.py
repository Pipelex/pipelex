from pathlib import Path

import pytest
from mthds.method_tree.models import TreeLimits
from mthds.method_tree.vocabulary import TreeRefusalCode
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pytest_mock import MockerFixture

from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.libraries.exceptions import HostLibraryTreeError, MethodTreeLoadError
from pipelex.libraries.method_trees import (
    LIMITS_ADVICE,
    bundle_files_under,
    list_library_bundle_files,
    list_library_dir_trees,
    list_local_method_tree,
    list_package_method_tree,
    reporting_host_library_tree_faults,
    submitted_tree_files,
    tree_python_sources,
)
from pipelex.methods.package_reason import MethodPackageReason

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
        # The caller reads the limit the tree passed, by the reason the listing stopped at it.
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.METHOD_PACKAGE_INVALID
        assert caller.params is not None
        assert caller.params.as_wire() == {"reason": MethodPackageReason.TOO_MANY_FILES, "limit": 1}

    def test_a_library_directory_holding_only_nested_methods_loads_them_all(self, tmp_path: Path) -> None:
        """Its own tree is empty, yet the packages and repositories nested in it load, and those nested in an empty one of them."""
        _touch(directory=tmp_path, tree_path=".hidden-notes.md", content="kept out")
        _touch(directory=tmp_path, tree_path="packages/invoicing/METHODS.toml", content=_MANIFEST)
        _touch(directory=tmp_path, tree_path="packages/invoicing/invoice.mthds")
        _touch(directory=tmp_path, tree_path="checkouts/reports/report.mthds")
        (tmp_path / "checkouts" / "reports" / ".git").mkdir()
        # A nested repository whose own tree is empty too, holding nothing but a nested package.
        (tmp_path / "checkouts" / "suite" / ".git").mkdir(parents=True)
        _touch(directory=tmp_path, tree_path="checkouts/suite/pkg/METHODS.toml", content=_MANIFEST)
        _touch(directory=tmp_path, tree_path="checkouts/suite/pkg/suite.mthds")
        # A directory the .gitignore keeps out is never entered, so the package under it is never reached, as in a listing.
        _touch(directory=tmp_path, tree_path=".gitignore", content="build/\n")
        _touch(directory=tmp_path, tree_path="build/stale/METHODS.toml", content=_MANIFEST)
        _touch(directory=tmp_path, tree_path="build/stale/stale.mthds")

        bundle_files = list_library_bundle_files(library_dirs=[tmp_path])

        by_location = {bundle_file.path: bundle_file.tree_bundle for bundle_file in bundle_files}
        assert set(by_location) == {
            tmp_path / "packages" / "invoicing" / "invoice.mthds",
            tmp_path / "checkouts" / "reports" / "report.mthds",
            tmp_path / "checkouts" / "suite" / "pkg" / "suite.mthds",
        }
        suite_tree = by_location[tmp_path / "checkouts" / "suite" / "pkg" / "suite.mthds"].tree
        assert suite_tree.directory == (tmp_path / "checkouts" / "suite" / "pkg").resolve()

    def test_a_nested_checkout_holding_no_bundle_is_skipped_before_it_is_listed(self, tmp_path: Path) -> None:
        """A nested repository with nothing to load never refuses the load, whatever it holds; one holding a bundle follows every rule."""
        _touch(directory=tmp_path, tree_path="top.mthds")
        _touch(directory=tmp_path, tree_path="vendor/tool/README.md", content="a tool")
        (tmp_path / "vendor" / "tool" / ".git").mkdir()
        (tmp_path / "vendor" / "tool" / "latest").symlink_to(tmp_path / "vendor" / "tool" / "README.md")

        assert [bundle_file.tree_bundle.tree_path for bundle_file in list_library_bundle_files(library_dirs=[tmp_path])] == ["top.mthds"]

        _touch(directory=tmp_path, tree_path="vendor/tool/tool.mthds")
        with pytest.raises(MethodTreeLoadError, match="symbolic link") as exc_info:
            list_library_bundle_files(library_dirs=[tmp_path])
        # The reason is the standard's refusal code, which the listing refused the tree with.
        assert exc_info.value.problem_params() == {"reason": TreeRefusalCode.SYMBOLIC_LINK}

    def test_this_machine_s_limits_are_read_once_per_listing(self, tmp_path: Path, mocker: MockerFixture) -> None:
        limits_spy = mocker.patch("pipelex.libraries.method_trees.local_tree_limits", return_value=TreeLimits())
        _touch(directory=tmp_path, tree_path="top.mthds")
        for name in ("one", "two"):
            _touch(directory=tmp_path, tree_path=f"packages/{name}/METHODS.toml", content=_MANIFEST)
            _touch(directory=tmp_path, tree_path=f"packages/{name}/{name}.mthds")

        assert len(list_library_bundle_files(library_dirs=[tmp_path, tmp_path / "packages"])) == 3
        limits_spy.assert_called_once()

    @pytest.mark.parametrize("refusal", ["symbolic_link", "limit"])
    def test_a_dependency_package_refusal_names_its_address_never_this_host_s_path(self, tmp_path: Path, refusal: str) -> None:
        package_root = tmp_path / "installed" / "invoicing"
        _touch(directory=package_root, tree_path="METHODS.toml", content=_MANIFEST)
        _touch(directory=package_root, tree_path="invoice.mthds")
        limits: TreeLimits | None = None
        if refusal == "symbolic_link":
            (package_root / "link.mthds").symlink_to(package_root / "invoice.mthds")
        else:
            limits = TreeLimits(max_files=1)

        with pytest.raises(MethodTreeLoadError) as exc_info:
            list_package_method_tree(root=package_root, package_address="github.com/pipelex-tests/invoicing", limits=limits)

        message = exc_info.value.message
        assert "github.com/pipelex-tests/invoicing" in message
        assert str(tmp_path) not in message
        assert str(tmp_path.resolve()) not in message
        assert LIMITS_ADVICE not in message

    def test_a_refused_tree_names_the_rule_and_the_path_a_caller_reads(self, tmp_path: Path) -> None:
        """`method.package_invalid` declares the rule broken and the tree path at fault, which reach a caller without the message."""
        _touch(directory=tmp_path, tree_path="method/main.mthds")
        (tmp_path / "method" / "link.mthds").symlink_to(tmp_path / "method" / "main.mthds")

        with pytest.raises(MethodTreeLoadError) as exc_info:
            list_local_method_tree(handed_over=tmp_path / "method")

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == "method.package_invalid"
        assert caller.params is not None
        assert caller.params.as_wire() == {"reason": "symbolic_link", "path": "link.mthds"}

    def test_a_refused_dependency_package_names_its_path_under_its_address(self, tmp_path: Path) -> None:
        package_root = tmp_path / "installed" / "invoicing"
        _touch(directory=package_root, tree_path="METHODS.toml", content=_MANIFEST)
        _touch(directory=package_root, tree_path="invoice.mthds")
        (package_root / "link.mthds").symlink_to(package_root / "invoice.mthds")

        with pytest.raises(MethodTreeLoadError) as exc_info:
            list_package_method_tree(root=package_root, package_address="github.com/pipelex-tests/invoicing")

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.params is not None
        assert caller.params.as_wire() == {"reason": "symbolic_link", "path": "github.com/pipelex-tests/invoicing/link.mthds"}

    def test_a_host_library_tree_that_cannot_be_listed_is_the_host_s_fault(self, tmp_path: Path) -> None:
        """Beside a caller's bundles, a tree of the host's own directories is no input of theirs, and its message never reaches them."""
        _touch(directory=tmp_path, tree_path="lib/a.mthds")
        (tmp_path / "lib" / "link.mthds").symlink_to(tmp_path / "lib" / "a.mthds")

        with pytest.raises(HostLibraryTreeError) as exc_info, reporting_host_library_tree_faults():
            list_library_bundle_files(library_dirs=[tmp_path / "lib"])

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == PipelexErrorCode.CONFIG_INVALID
        assert caller.domain == ProblemDomain.OPERATOR
        assert exc_info.value.message not in str(caller.to_wire())
        assert isinstance(exc_info.value.__cause__, MethodTreeLoadError)

    def test_every_bundle_file_under_a_directory_is_found_whatever_the_membership_rule(self, tmp_path: Path) -> None:
        """The superset a verdict's withholding falls back to when listing the trees fails: it never raises."""
        _touch(directory=tmp_path, tree_path="lib/a.mthds")
        _touch(directory=tmp_path, tree_path="lib/.hidden/b.mthds")
        (tmp_path / "lib" / "link.mthds").symlink_to(tmp_path / "lib" / "a.mthds")

        found = bundle_files_under(library_dirs=[tmp_path / "lib", tmp_path / "missing"])

        assert set(found) == {tmp_path / "lib" / "a.mthds", tmp_path / "lib" / ".hidden" / "b.mthds", tmp_path / "lib" / "link.mthds"}

    def test_only_a_directory_whose_own_tree_holds_no_bundle_submits_its_files(self, tmp_path: Path) -> None:
        """Its files are the Python submitted beside bundles parsed from strings; a tree holding a bundle carries its own."""
        _touch(directory=tmp_path, tree_path="submitted/funcs/totals.py", content="X = 1\n")
        _touch(directory=tmp_path, tree_path="submitted/notes.txt", content="note\n")
        _touch(directory=tmp_path, tree_path="method/method.mthds")
        _touch(directory=tmp_path, tree_path="method/funcs.py", content="X = 2\n")
        _touch(directory=tmp_path, tree_path="rooted/METHODS.toml", content=_MANIFEST)
        _touch(directory=tmp_path, tree_path="rooted/python/helpers.py", content="X = 3\n")

        submitted = {
            library_tree.library_dir.name: {
                path: held_file.source.read_bytes() if isinstance(held_file.source, Path) else held_file.source
                for path, held_file in submitted_tree_files(library_tree=library_tree).items()
            }
            for library_tree in list_library_dir_trees(library_dirs=[tmp_path / "submitted", tmp_path / "method", tmp_path / "rooted" / "python"])
        }

        assert submitted == {"submitted": {"funcs/totals.py": b"X = 1\n", "notes.txt": b"note\n"}, "method": {}, "python": {"helpers.py": b"X = 3\n"}}

    def test_the_python_of_a_nested_tree_is_named_from_its_library_directory(self, tmp_path: Path) -> None:
        _touch(directory=tmp_path, tree_path="top.mthds")
        _touch(directory=tmp_path, tree_path="top_funcs.py", content="X = 1\n")
        _touch(directory=tmp_path, tree_path="checkouts/reports/report.mthds")
        _touch(directory=tmp_path, tree_path="checkouts/reports/models/report.py", content="X = 2\n")
        (tmp_path / "checkouts" / "reports" / ".git").mkdir()

        sources: dict[str, str] = {}
        for library_tree in list_library_dir_trees(library_dirs=[tmp_path]):
            sources.update(tree_python_sources(tree=library_tree.tree, library_dir=library_tree.library_dir))

        assert sources == {"top_funcs.py": "X = 1\n", "checkouts/reports/models/report.py": "X = 2\n"}

    def test_a_directory_named_like_an_inputs_file_is_entered_and_kept(self, tmp_path: Path) -> None:
        """A directory named like a run's inputs file is an ordinary directory: the scan enters `inputs.json/` and its bundle loads."""
        _touch(directory=tmp_path, tree_path="top.mthds")
        _touch(directory=tmp_path, tree_path="vendor/tool/inputs.json/flow.mthds")
        _touch(directory=tmp_path, tree_path="vendor/tool/inputs.toml/notes.md", content="kept")
        (tmp_path / "vendor" / "tool" / ".git").mkdir()

        library_trees = list_library_dir_trees(library_dirs=[tmp_path])

        tool_tree = next(
            library_tree.tree for library_tree in library_trees if library_tree.tree.directory == (tmp_path / "vendor" / "tool").resolve()
        )
        assert tool_tree.tree_paths == ["inputs.json/flow.mthds", "inputs.toml/notes.md"]
        bundle_paths = {bundle_file.path for bundle_file in list_library_bundle_files(library_dirs=[tmp_path])}
        assert bundle_paths == {tmp_path / "top.mthds", tmp_path / "vendor" / "tool" / "inputs.json" / "flow.mthds"}

    @pytest.mark.xfail(
        raises=MethodTreeLoadError,
        reason="The run-inputs default is applied by the mthds lister from the mthds release implementing it, not pinned yet",
    )
    def test_a_run_s_inputs_file_is_no_member_of_any_tree_at_any_depth(self, tmp_path: Path) -> None:
        """An inputs.json or inputs.toml, regular file or link never followed, stays out at the root and below; names match byte for byte."""
        outside = _touch(directory=tmp_path, tree_path="outside/secrets.json", content='{"token": "x"}')
        method_dir = tmp_path / "method"
        _touch(directory=method_dir, tree_path="method.mthds")
        _touch(directory=method_dir, tree_path="inputs.json", content='{"topic": "cats"}')
        _touch(directory=method_dir, tree_path="steps/inputs.toml", content='topic = "cats"\n')
        _touch(directory=method_dir, tree_path="cases/Inputs.json", content="{}")
        (method_dir / "examples").mkdir()
        (method_dir / "examples" / "inputs.json").symlink_to(outside)

        (library_tree,) = list_library_dir_trees(library_dirs=[method_dir])

        assert library_tree.tree.tree_paths == ["cases/Inputs.json", "method.mthds"]
