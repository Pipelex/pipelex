import sys
from pathlib import Path

import pytest

from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    import_module_from_file,
)


class TestImportModuleFromFile:
    @pytest.fixture(autouse=True)
    def cleanup_sys_modules(self):
        """Clean up sys.modules entries after each test."""
        yield
        # Clean up sys.modules entries for test modules
        modules_to_remove = [name for name in sys.modules if "test_module_" in name or name == "test_module"]
        for module_name in modules_to_remove:
            del sys.modules[module_name]

    def test_import_valid_python_file(self, tmp_path: Path):
        """Test importing a valid Python file."""
        test_file_path = tmp_path / "test_module_valid.py"
        test_file_path.write_text("""
def test_function():
    return "test_value"

class TestClass:
    pass
""")
        module = import_module_from_file(str(test_file_path))
        assert hasattr(module, "test_function")
        assert hasattr(module, "TestClass")
        assert module.test_function() == "test_value"

    def test_import_non_python_file_raises_error(self, tmp_path: Path):
        """Test that importing a non-Python file raises ModuleFileError."""
        test_file_path = tmp_path / "test_file.txt"
        test_file_path.write_text("This is not Python code")
        with pytest.raises(ModuleFileError) as excinfo:
            import_module_from_file(str(test_file_path))
        assert "is not a Python file" in str(excinfo.value)

    def test_import_nonexistent_file_raises_error(self, tmp_path: Path):
        """Test that importing a nonexistent file raises FileNotFoundError."""
        nonexistent_file_path = tmp_path / "nonexistent.py"
        with pytest.raises(FileNotFoundError):
            import_module_from_file(str(nonexistent_file_path))

    def test_import_file_with_syntax_error_raises_error(self, tmp_path: Path):
        """Test that importing a file with syntax errors raises SyntaxError."""
        test_file_path = tmp_path / "syntax_error.py"
        test_file_path.write_text("""
def test_function(
    return "missing closing parenthesis"
""")
        with pytest.raises(SyntaxError):
            import_module_from_file(str(test_file_path))

    def test_import_file_with_import_error_raises_error(self, tmp_path: Path):
        """Test that importing a file with import errors raises ImportError."""
        test_file_path = tmp_path / "import_error.py"
        test_file_path.write_text("""
import nonexistent_module
""")
        with pytest.raises(ImportError):
            import_module_from_file(str(test_file_path))

    def test_module_added_to_sys_modules(self, tmp_path: Path):
        """Test that imported module is added to sys.modules."""
        test_file_path = tmp_path / "test_module_sys.py"
        test_file_path.write_text("""
def test_function():
    return "test_value"
""")
        module = import_module_from_file(str(test_file_path))
        # The module name is derived from the full file path
        module_name = module.__name__
        assert module_name.endswith("test_module_sys")
        assert module_name in sys.modules
        assert sys.modules[module_name] is module

    def test_module_name_with_path_separators(self, tmp_path: Path):
        """Test that module name is correctly formatted with path separators (should use file basename)."""
        nested_dir = tmp_path / "nested" / "subdir"
        nested_dir.mkdir(parents=True)
        test_file_path = nested_dir / "test_module_nested.py"
        test_file_path.write_text("""
def test_function():
    return "test_value"
""")
        module = import_module_from_file(str(test_file_path))
        assert hasattr(module, "test_function")
        assert module.test_function() == "test_value"
