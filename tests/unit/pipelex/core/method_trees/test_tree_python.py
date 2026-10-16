import sys
from pathlib import Path

import pytest
from mthds.method_tree.lister import list_method_tree
from mthds.method_tree.models import MethodTree

from pipelex.core.method_trees.exceptions import TreeModuleExcludedError, TreeModuleShadowingError, TreePythonError, TreePythonHeldError
from pipelex.core.method_trees.tree_python import TREE_PYTHON_HOLD, import_held_tree_module


def _write_tree(*, root: Path, files: dict[str, str]) -> MethodTree:
    for tree_path, text in files.items():
        target = root.joinpath(*tree_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return list_method_tree(root)


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

        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-alpha")
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
        TREE_PYTHON_HOLD.acquire(tree=first, holder="run-first")
        TREE_PYTHON_HOLD.acquire(tree=first, holder="run-first-again")

        with pytest.raises(TreePythonHeldError) as exc_info:
            TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second")

        assert str((tmp_path / "first").resolve()) in exc_info.value.message
        assert str((tmp_path / "second").resolve()) in exc_info.value.message

        TREE_PYTHON_HOLD.release(holder="run-first")
        with pytest.raises(TreePythonHeldError):
            TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second")

        TREE_PYTHON_HOLD.release(holder="run-first-again")
        second_identity = TREE_PYTHON_HOLD.acquire(tree=second, holder="run-second")
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
            TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-shadow")

        assert expected_message in exc_info.value.message
        assert module_file in exc_info.value.message

    def test_the_structures_module_is_the_one_a_tree_may_ship(self, tmp_path: Path) -> None:
        tree = _write_tree(root=tmp_path / "structured", files={"structured.mthds": 'domain = "structured"\n', "structures.py": "X = 1\n"})

        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-structured")

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
        identity = TREE_PYTHON_HOLD.acquire(tree=tree, holder="run-guarded")

        with pytest.raises(TreeModuleExcludedError) as exc_info:
            import_held_tree_module(identity=identity, module_name="tree_probe_guarded")

        assert "tree_probe_scratch" in str(exc_info.value)
        assert "the membership rule excludes it" in str(exc_info.value)
        assert "tree_probe_scratch" not in sys.modules

    def test_a_tree_read_without_a_directory_holds_no_python(self, tmp_path: Path) -> None:
        bundle = tmp_path / "lone.mthds"
        bundle.write_text('domain = "lone"\n', encoding="utf-8")

        with pytest.raises(TreePythonError, match="read alone, as a one-file tree"):
            TREE_PYTHON_HOLD.acquire(tree=list_method_tree(bundle), holder="run-lone")
