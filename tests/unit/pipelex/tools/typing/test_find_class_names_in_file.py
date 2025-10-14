from pathlib import Path

import pytest

from pipelex.tools.typing.module_inspector import (
    ModuleFileError,
    find_class_names_in_file,
)


class TestFindClassNamesInFile:
    def test_find_all_class_names(self, tmp_path: Path):
        """Test finding all class names without filtering."""
        test_file_path = tmp_path / "test_classes.py"
        test_file_path.write_text("""
class ClassA:
    pass

class ClassB:
    pass

def some_function():
    pass
""")
        class_names = find_class_names_in_file(str(test_file_path))
        assert len(class_names) == 2
        assert "ClassA" in class_names
        assert "ClassB" in class_names

    def test_find_class_names_with_base_class_filter(self, tmp_path: Path):
        """Test finding classes that inherit from specific base classes."""
        test_file_path = tmp_path / "test_inheritance.py"
        test_file_path.write_text("""
class BaseContent:
    pass

class StructuredContent:
    pass

class MyContent(StructuredContent):
    pass

class OtherContent(BaseContent):
    pass

class UnrelatedClass:
    pass
""")
        class_names = find_class_names_in_file(
            str(test_file_path),
            base_class_names=["StructuredContent"],
        )
        assert len(class_names) == 1
        assert "MyContent" in class_names
        assert "OtherContent" not in class_names
        assert "UnrelatedClass" not in class_names

    def test_find_class_names_with_qualified_base_class(self, tmp_path: Path):
        """Test finding classes with qualified base class names."""
        test_file_path = tmp_path / "test_qualified.py"
        test_file_path.write_text("""
from pipelex.core.stuffs.structured_content import StructuredContent

class MyContent(StructuredContent):
    pass

class UnrelatedClass:
    pass
""")
        class_names = find_class_names_in_file(
            str(test_file_path),
            base_class_names=["StructuredContent"],
        )
        assert len(class_names) == 1
        assert "MyContent" in class_names

    def test_find_class_names_empty_file(self, tmp_path: Path):
        """Test with file containing no classes."""
        test_file_path = tmp_path / "test_empty.py"
        test_file_path.write_text("""
def some_function():
    pass

variable = 42
""")
        class_names = find_class_names_in_file(str(test_file_path))
        assert len(class_names) == 0

    def test_find_class_names_non_python_file_raises_error(self, tmp_path: Path):
        """Test that non-Python file raises error."""
        test_file_path = tmp_path / "test.txt"
        test_file_path.write_text("Not Python")
        with pytest.raises(ModuleFileError) as excinfo:
            find_class_names_in_file(str(test_file_path))
        assert "is not a Python file" in str(excinfo.value)

    def test_find_class_names_nonexistent_file_raises_error(self, tmp_path: Path):
        """Test that nonexistent file raises error."""
        nonexistent_file_path = tmp_path / "nonexistent.py"
        with pytest.raises(ModuleFileError) as excinfo:
            find_class_names_in_file(str(nonexistent_file_path))
        assert "does not exist" in str(excinfo.value)
