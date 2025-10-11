import os
import shutil
import sys
import types
from pathlib import Path

import pytest

from pipelex.tools.typing.module_inspector import ModuleFileError, find_classes_in_module, import_module_from_file


class TestModuleFileError:
    def test_exception_inheritance(self):
        """Test that ModuleFileError inherits from Exception."""
        error = ModuleFileError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"


class TestImportModuleFromFile:
    @pytest.fixture(autouse=True)
    def cleanup_test_files(self):
        """Clean up test files and sys.modules after each test."""
        yield
        # Clean up test files
        test_files = ["test_module.py", "test_file.txt", "syntax_error.py", "import_error.py", "nested/subdir/test_module.py"]
        for file_path in test_files:
            if os.path.exists(file_path):
                os.remove(file_path)

        # Clean up nested directories and __pycache__ directories
        directories_to_remove = ["nested/subdir", "nested", "__pycache__", "nested/__pycache__", "nested/subdir/__pycache__"]
        for dir_path in directories_to_remove:
            if Path(dir_path).exists():
                shutil.rmtree(dir_path)

        # Clean up sys.modules entries for test modules
        modules_to_remove = [name for name in sys.modules if name.startswith("test_module")]
        for module_name in modules_to_remove:
            del sys.modules[module_name]

    def test_import_valid_python_file(self):
        """Test importing a valid Python file."""
        test_file_path = "test_module.py"
        with open(test_file_path, "w") as test_file:
            test_file.write("""
def test_function():
    return "test_value"

class TestClass:
    pass
""")
        module = import_module_from_file(test_file_path)
        assert hasattr(module, "test_function")
        assert hasattr(module, "TestClass")
        assert module.test_function() == "test_value"

    def test_import_non_python_file_raises_error(self):
        """Test that importing a non-Python file raises ModuleFileError."""
        test_file_path = "test_file.txt"
        with open(test_file_path, "w") as test_file:
            test_file.write("This is not Python code")
        with pytest.raises(ModuleFileError) as excinfo:
            import_module_from_file(test_file_path)
        assert "is not a Python file" in str(excinfo.value)

    def test_import_nonexistent_file_raises_error(self):
        """Test that importing a nonexistent file raises FileNotFoundError."""
        nonexistent_file_path = "nonexistent.py"
        with pytest.raises(FileNotFoundError):
            import_module_from_file(nonexistent_file_path)

    def test_import_file_with_syntax_error_raises_error(self):
        """Test that importing a file with syntax errors raises SyntaxError."""
        test_file_path = "syntax_error.py"
        with open(test_file_path, "w") as test_file:
            test_file.write("""
def test_function(
    return "missing closing parenthesis"
""")
        with pytest.raises(SyntaxError):
            import_module_from_file(test_file_path)

    def test_import_file_with_import_error_raises_error(self):
        """Test that importing a file with import errors raises ImportError."""
        test_file_path = "import_error.py"
        with open(test_file_path, "w") as test_file:
            test_file.write("""
import nonexistent_module
""")
        with pytest.raises(ImportError):
            import_module_from_file(test_file_path)

    def test_module_added_to_sys_modules(self):
        """Test that imported module is added to sys.modules."""
        test_file_path = "test_module.py"
        with open(test_file_path, "w") as test_file:
            test_file.write("""
def test_function():
    return "test_value"
""")
        module = import_module_from_file(test_file_path)
        # The module name should be the actual module path derived from the file path
        expected_module_name = "test_module"
        assert module.__name__ == expected_module_name
        assert expected_module_name in sys.modules
        assert sys.modules[expected_module_name] is module

    def test_module_name_with_path_separators(self):
        """Test that module name is correctly formatted with path separators (should use file basename)."""
        test_file_path = "nested/subdir/test_module.py"
        # Create nested directories
        os.makedirs("nested/subdir", exist_ok=True)
        with open(test_file_path, "w") as test_file:
            test_file.write("""
def test_function():
    return "test_value"
""")
        module = import_module_from_file(test_file_path)
        assert hasattr(module, "test_function")
        assert module.test_function() == "test_value"


class TestFindClassesInModule:
    def test_find_all_classes_no_base_class(self):
        """Test finding all classes when no base class is specified."""
        test_module = types.ModuleType("test_module")

        class ClassA:
            pass

        class ClassB:
            pass

        # Set __module__ so inspect.getmembers finds them
        ClassA.__module__ = test_module.__name__
        ClassB.__module__ = test_module.__name__
        test_module.ClassA = ClassA  # type: ignore[attr-defined]
        test_module.ClassB = ClassB  # type: ignore[attr-defined]
        test_module.some_function = lambda: None  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert ClassA in classes
        assert ClassB in classes

    def test_find_classes_with_base_class(self):
        """Test finding classes that inherit from a specific base class."""
        test_module = types.ModuleType("test_module")

        class BaseClass:
            pass

        class SubClass(BaseClass):
            pass

        class UnrelatedClass:
            pass

        # Set __module__
        BaseClass.__module__ = test_module.__name__
        SubClass.__module__ = test_module.__name__
        UnrelatedClass.__module__ = test_module.__name__
        test_module.BaseClass = BaseClass  # type: ignore[attr-defined]
        test_module.SubClass = SubClass  # type: ignore[attr-defined]
        test_module.UnrelatedClass = UnrelatedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert SubClass in classes
        assert UnrelatedClass not in classes

    def test_find_classes_exclude_imported(self):
        """Test that imported classes are excluded when include_imported=False."""
        test_module = types.ModuleType("test_module")

        class LocalClass:
            pass

        class ImportedClass:
            pass

        LocalClass.__module__ = test_module.__name__
        ImportedClass.__module__ = "other_module"
        test_module.LocalClass = LocalClass  # type: ignore[attr-defined]
        test_module.ImportedClass = ImportedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert LocalClass in classes
        assert ImportedClass not in classes

    def test_find_classes_include_imported(self):
        """Test that imported classes are included when include_imported=True."""
        test_module = types.ModuleType("test_module")

        class LocalClass:
            pass

        class ImportedClass:
            pass

        LocalClass.__module__ = test_module.__name__
        ImportedClass.__module__ = "other_module"
        test_module.LocalClass = LocalClass  # type: ignore[attr-defined]
        test_module.ImportedClass = ImportedClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=True)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert LocalClass in classes
        assert ImportedClass in classes

    def test_find_classes_empty_module(self):
        """Test finding classes in an empty module."""
        test_module = types.ModuleType("test_module")
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 0
        assert len(classes) == expected_number_of_classes

    def test_find_classes_with_functions_and_variables(self):
        """Test that functions and variables are not included in class search."""
        test_module = types.ModuleType("test_module")

        class TestClass:
            pass

        TestClass.__module__ = test_module.__name__

        def test_function():
            pass

        test_module.TestClass = TestClass  # type: ignore[attr-defined]
        test_module.test_function = test_function  # type: ignore[attr-defined]
        test_module.some_variable = 42  # type: ignore[attr-defined]
        test_module.some_string = "hello"  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert TestClass in classes

    def test_find_classes_with_nested_classes(self):
        """Test finding classes including nested classes."""
        test_module = types.ModuleType("test_module")

        class OuterClass:
            class InnerClass:
                pass

        OuterClass.__module__ = test_module.__name__
        test_module.OuterClass = OuterClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 1
        assert len(classes) == expected_number_of_classes
        assert OuterClass in classes

    def test_find_classes_with_builtin_types(self):
        """Test finding classes including user-defined types (not builtins, which can't be assigned __module__)."""
        test_module = types.ModuleType("test_module")

        class MyClassA:
            pass

        class MyClassB:
            pass

        MyClassA.__module__ = test_module.__name__
        MyClassB.__module__ = test_module.__name__
        test_module.MyClassA = MyClassA  # type: ignore[attr-defined]
        test_module.MyClassB = MyClassB  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=None, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert MyClassA in classes
        assert MyClassB in classes

    def test_find_classes_with_base_class_and_imported(self):
        test_module = types.ModuleType("test_module")

        class BaseClass:
            pass

        class LocalSubClass(BaseClass):
            pass

        class ImportedSubClass(BaseClass):
            pass

        BaseClass.__module__ = test_module.__name__
        LocalSubClass.__module__ = test_module.__name__
        ImportedSubClass.__module__ = "other_module"
        test_module.BaseClass = BaseClass  # type: ignore[attr-defined]
        test_module.LocalSubClass = LocalSubClass  # type: ignore[attr-defined]
        test_module.ImportedSubClass = ImportedSubClass  # type: ignore[attr-defined]
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=False)
        expected_number_of_classes = 2
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert LocalSubClass in classes
        assert ImportedSubClass not in classes
        classes = find_classes_in_module(test_module, base_class=BaseClass, include_imported=True)
        expected_number_of_classes = 3
        assert len(classes) == expected_number_of_classes
        assert BaseClass in classes
        assert LocalSubClass in classes
        assert ImportedSubClass in classes
