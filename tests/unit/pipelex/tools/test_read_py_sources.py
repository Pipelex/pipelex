import sys
from pathlib import Path

from pipelex.system.registries.func_registry_utils import FuncRegistryUtils


class TestReadPySources:
    """read_py_sources captures every .py as text, recursively, WITHOUT ever importing it."""

    def test_captures_nested_sources_without_importing(self, tmp_path: Path):
        """Nested .py files are captured by POSIX relpath, and no file is imported (sys.modules untouched).

        Each fixture file imports a module that does not exist: if read_py_sources imported any of
        them, the import would raise ModuleNotFoundError. It must not — it only reads the bytes.
        """
        top_source = "import this_module_does_not_exist_top  # noqa\n\nTOP = 1\n"
        nested_source = "import this_module_does_not_exist_nested  # noqa\n\nNESTED = 2\n"
        (tmp_path / "top.py").write_text(top_source, encoding="utf-8")
        nested_dir = tmp_path / "structures"
        nested_dir.mkdir()
        (nested_dir / "item.py").write_text(nested_source, encoding="utf-8")

        modules_before = set(sys.modules)

        sources = FuncRegistryUtils.read_py_sources(folder_path=tmp_path)

        assert sources == {
            "top.py": top_source,
            "structures/item.py": nested_source,
        }
        # No import happened: the phantom modules are absent and sys.modules is unchanged.
        assert "this_module_does_not_exist_top" not in sys.modules
        assert "this_module_does_not_exist_nested" not in sys.modules
        assert set(sys.modules) == modules_before

    def test_empty_folder_returns_empty(self, tmp_path: Path):
        """A folder with no Python files yields an empty mapping."""
        assert FuncRegistryUtils.read_py_sources(folder_path=tmp_path) == {}
