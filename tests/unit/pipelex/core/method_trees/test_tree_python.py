import importlib.util
import json
import sys
from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree
from mthds.method_tree.models import MethodTree
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.core.method_trees import tree_python
from pipelex.core.method_trees.exceptions import TreeModuleExcludedError, TreeModuleShadowingError, TreePythonError, TreePythonHeldError
from pipelex.core.method_trees.tree_python import (
    TREE_PYTHON_HOLD,
    check_tree_module_names,
    import_held_tree_module,
    sharing_module_name_checks,
)
from pipelex.errors.problem import ProblemView
from pipelex.tools.typing.module_inspector import import_module_from_file

_LABEL = "the method tree holding probe.mthds"


def _write_tree(*, root: Path, files: dict[str, str]) -> MethodTree:
    for tree_path, text in files.items():
        target = root.joinpath(*tree_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return list_method_tree(root)


def _host_paths(*, tmp_path: Path) -> list[str]:
    """The spellings of the test's directory on this host, which no message may name (`/var` is `/private/var` on macOS)."""
    return [str(tmp_path), str(tmp_path.resolve())]


def _helper_tree(*, root: Path, value: str) -> MethodTree:
    """A tree whose structure module imports a sibling helper by its top-level name, as a step's module does."""
    return _write_tree(
        root=root,
        files={
            "probe.mthds": 'domain = "probe"\n',
            "tree_probe_helpers.py": f"VALUE = {value!r}\n",
            "tree_probe_shapes.py": "import tree_probe_helpers\n\nSHAPE = tree_probe_helpers.VALUE\n",
            "tree_probe_steps.py": "from tree_probe_helpers import VALUE\n",
        },
    )


@pytest.mark.usefixtures("released_hold")
class TestTreePython:
    def test_a_held_tree_imports_by_real_name_writes_no_bytecode_and_is_evicted(self, tmp_path: Path) -> None:
        tree = _write_tree(
            root=tmp_path / "alpha",
            files={
                "alpha.mthds": 'domain = "alpha"\n',
                "tree_probe_alpha/__init__.py": "",
                "tree_probe_alpha/rates.py": "VAT_PERCENT = 20\n",
                "tree_probe_alpha/totals.py": "from tree_probe_alpha.rates import VAT_PERCENT\n\nTOTAL = 100 + VAT_PERCENT\n",
            },
        )

        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-alpha", label=_LABEL)
        module = import_held_tree_module(identity=identity, module_name="tree_probe_alpha.totals")

        assert module.TOTAL == 120
        assert module.__name__ == "tree_probe_alpha.totals"
        assert sys.path[0] == str(identity.root)
        assert not list((tmp_path / "alpha").rglob("__pycache__"))

        TREE_PYTHON_HOLD.release(holder="run-alpha")
        TREE_PYTHON_HOLD.unload_if_unheld()

        assert "tree_probe_alpha.totals" not in sys.modules
        assert "tree_probe_alpha" not in sys.modules
        assert str(identity.root) not in sys.path

    def test_another_tree_is_refused_while_one_is_held_naming_both(self, tmp_path: Path) -> None:
        first = _write_tree(root=tmp_path / "first", files={"first.mthds": 'domain = "first"\n', "tree_probe_first.py": "X = 1\n"})
        second = _write_tree(root=tmp_path / "second", files={"second.mthds": 'domain = "second"\n', "tree_probe_second.py": "X = 2\n"})
        TREE_PYTHON_HOLD.acquire(tree=first, holder="run-first", label=_LABEL)
        TREE_PYTHON_HOLD.acquire(tree=first, holder="run-first-again", label=_LABEL)

        with pytest.raises(TreePythonHeldError) as exc_info:
            TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second", label="the method tree holding second.mthds")

        assert f"the method tree holding second.mthds ({second.digest[:19]})" in exc_info.value.message
        assert f"({first.digest[:19]})" in exc_info.value.message

        TREE_PYTHON_HOLD.release(holder="run-first")
        with pytest.raises(TreePythonHeldError):
            TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second", label=_LABEL)

        TREE_PYTHON_HOLD.release(holder="run-first-again")
        second_identity = TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second", label=_LABEL)
        assert import_held_tree_module(identity=second_identity, module_name="tree_probe_second").X == 2

    @pytest.mark.parametrize(
        ("module_file", "expected_message"),
        [
            pytest.param("json.py", "the standard-library module 'json'", id="standard-library"),
            pytest.param("pytest.py", "the module 'pytest', already imported in this process", id="imported-package"),
        ],
    )
    def test_a_module_that_would_shadow_another_is_refused(self, tmp_path: Path, module_file: str, expected_message: str) -> None:
        tree = _write_tree(root=tmp_path / "shadow", files={"shadow.mthds": 'domain = "shadow"\n', module_file: "X = 1\n"})

        with pytest.raises(TreeModuleShadowingError) as exc_info:
            TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-shadow", label=_LABEL)

        assert expected_message in exc_info.value.message
        assert module_file in exc_info.value.message

    def test_the_structures_module_is_the_one_a_tree_may_ship(self, tmp_path: Path) -> None:
        tree = _write_tree(root=tmp_path / "structured", files={"structured.mthds": 'domain = "structured"\n', "structures.py": "X = 1\n"})

        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-structured", label=_LABEL)

        assert TREE_PYTHON_HOLD.is_held(identity=identity)

    def test_an_import_of_a_file_the_tree_keeps_out_is_refused_with_the_rule(self, tmp_path: Path) -> None:
        tree = _write_tree(
            root=tmp_path / "guarded",
            files={
                "guarded.mthds": 'domain = "guarded"\n',
                ".gitignore": "tree_probe_scratch.py\n",
                "tree_probe_scratch.py": "SECRET = 1\n",
                "tree_probe_guarded.py": "import tree_probe_scratch\n",
            },
        )
        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-guarded", label=_LABEL)

        with pytest.raises(TreeModuleExcludedError) as exc_info:
            import_held_tree_module(identity=identity, module_name="tree_probe_guarded")

        assert "tree_probe_scratch" in str(exc_info.value)
        assert "the membership rule excludes it" in str(exc_info.value)
        assert "tree_probe_scratch" not in sys.modules

    def test_a_tree_read_without_a_directory_holds_no_python(self, tmp_path: Path) -> None:
        bundle = tmp_path / "lone.mthds"
        bundle.write_text('domain = "lone"\n', encoding="utf-8")

        with pytest.raises(TreePythonError, match="read alone, as a one-file tree"):
            TREE_PYTHON_HOLD.acquire(tree=list_method_tree(bundle), holder="run-lone", label=_LABEL)

    def test_a_helper_a_structure_module_imported_while_loading_is_evicted_with_its_tree(self, tmp_path: Path) -> None:
        first = _helper_tree(root=tmp_path / "first", value="first")
        second = _helper_tree(root=tmp_path / "second", value="second")
        # A library load imports a structure module by its file, its directory first on the import path, and the module
        # imports its sibling helper with Python's own loader, under the helper's top-level name.
        import_module_from_file((tmp_path / "first" / "tree_probe_shapes.py").resolve())
        assert sys.modules["tree_probe_helpers"].VALUE == "first"
        first_identity = TREE_PYTHON_HOLD.acquire(tree=first, holder="run-first", label=_LABEL)
        assert import_held_tree_module(identity=first_identity, module_name="tree_probe_steps").VALUE == "first"
        TREE_PYTHON_HOLD.release(holder="run-first")

        second_identity = TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second", label=_LABEL)
        module = import_held_tree_module(identity=second_identity, module_name="tree_probe_steps")

        assert module.VALUE == "second"
        assert sys.modules["tree_probe_helpers"].VALUE == "second"
        first_root = str((tmp_path / "first").resolve())
        assert first_root not in sys.path

    def test_a_released_tree_leaves_the_import_path_until_it_is_held_again(self, tmp_path: Path) -> None:
        tree = _write_tree(root=tmp_path / "between", files={"between.mthds": 'domain = "between"\n', "tree_probe_between.py": "X = 1\n"})
        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-between", label=_LABEL)
        assert sys.path[0] == str(identity.root)

        TREE_PYTHON_HOLD.release(holder="run-between")

        assert str(identity.root) not in sys.path
        assert importlib.util.find_spec("tree_probe_between") is None
        held_again = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-between-again", label=_LABEL)
        assert sys.path[0] == str(identity.root)
        assert import_held_tree_module(identity=held_again, module_name="tree_probe_between").X == 1

    def test_a_module_under_the_root_that_the_tree_keeps_out_is_not_evicted(self, tmp_path: Path) -> None:
        first = _write_tree(
            root=tmp_path / "rooted",
            files={"rooted.mthds": 'domain = "rooted"\n', "tree_probe_rooted.py": "X = 1\n", "venv/pyvenv.cfg": "home = /usr\n"},
        )
        site_module_file = tmp_path / "rooted" / "venv" / "tree_probe_site.py"
        site_module_file.write_text("SITE = 1\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location("tree_probe_site", site_module_file)
        assert spec is not None
        assert spec.loader is not None
        site_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(site_module)
        sys.modules["tree_probe_site"] = site_module
        second = _write_tree(root=tmp_path / "other", files={"other.mthds": 'domain = "other"\n', "tree_probe_other.py": "X = 2\n"})
        try:
            first_identity = TREE_PYTHON_HOLD.acquire(tree=first, holder="run-rooted", label=_LABEL)
            import_held_tree_module(identity=first_identity, module_name="tree_probe_rooted")
            TREE_PYTHON_HOLD.release(holder="run-rooted")

            TREE_PYTHON_HOLD.acquire(tree=second, holder="run-other", label=_LABEL)

            assert "tree_probe_rooted" not in sys.modules
            assert sys.modules["tree_probe_site"] is site_module
        finally:
            sys.modules.pop("tree_probe_site", None)

    def test_the_errors_of_a_tree_name_no_path_of_this_host(self, tmp_path: Path) -> None:
        shadowing = _write_tree(root=tmp_path / "shadowing", files={"shadowing.mthds": 'domain = "shadowing"\n', "json.py": "X = 1\n"})
        with pytest.raises(TreeModuleShadowingError) as shadowing_info:
            TREE_PYTHON_HOLD.acquire(tree=shadowing, holder="run-shadowing", label="the method tree holding shadowing.mthds")
        shadowing_problem = shadowing_info.value.to_problem(view=ProblemView.CALLER)
        assert shadowing_problem.code == CoreCode.METHOD_NAME_CONFLICT
        operator_report = json.dumps(shadowing_info.value.to_problem(view=ProblemView.OPERATOR).to_wire())
        assert "the method tree holding shadowing.mthds" in operator_report
        assert "json.py" in operator_report

        guarded = _write_tree(
            root=tmp_path / "guarded",
            files={
                "guarded.mthds": 'domain = "guarded"\n',
                ".gitignore": "tree_probe_hidden.py\n",
                "tree_probe_hidden.py": "X = 1\n",
                "tree_probe_reaches.py": "import tree_probe_hidden\n",
            },
        )
        guarded_identity = TREE_PYTHON_HOLD.acquire(tree=guarded, holder="run-guarded", label="the method tree holding guarded.mthds")
        with pytest.raises(TreeModuleExcludedError) as excluded_info:
            import_held_tree_module(identity=guarded_identity, module_name="tree_probe_reaches")
        assert "the file tree_probe_hidden.py of the method tree holding guarded.mthds" in excluded_info.value.message

        other = _write_tree(root=tmp_path / "other", files={"other.mthds": 'domain = "other"\n', "tree_probe_other.py": "X = 2\n"})
        with pytest.raises(TreePythonHeldError) as held_info:
            TREE_PYTHON_HOLD.acquire(tree=other, holder="run-other", label="the method tree holding other.mthds")

        # The excluded-module refusal is an ImportError the import machinery raises, read by its message alone.
        caller_reports = [json.dumps(error.to_problem(view=ProblemView.CALLER).to_wire()) for error in (shadowing_info.value, held_info.value)]
        for message in (operator_report, excluded_info.value.message, held_info.value.message, *caller_reports):
            for host_path in _host_paths(tmp_path=tmp_path):
                assert host_path not in message

    def test_a_load_judges_a_tree_s_module_names_once_for_all_its_steps(self, tmp_path: Path, mocker: MockerFixture) -> None:
        judged_spy = mocker.spy(tree_python, "_module_outside_tree")
        top_level_modules = {"tree_probe_first": "tree_probe_first.py", "tree_probe_second": "tree_probe_second/rates.py"}

        with sharing_module_name_checks():
            for _step in range(3):
                check_tree_module_names(top_level_modules=top_level_modules, tree_label=_LABEL, root=tmp_path, checks_this_process=True)
        assert judged_spy.call_count == len(top_level_modules)

        check_tree_module_names(top_level_modules=top_level_modules, tree_label=_LABEL, root=tmp_path, checks_this_process=True)
        assert judged_spy.call_count == 2 * len(top_level_modules)
