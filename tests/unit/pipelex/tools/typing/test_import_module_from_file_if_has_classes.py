import sys
from pathlib import Path

import pytest

from pipelex.tools.typing.module_inspector import import_module_from_file_if_has_classes


class TestImportModuleFromFileIfHasClasses:
    @pytest.fixture(autouse=True)
    def cleanup_sys_modules(self):
        """Clean up sys.modules entries after each test."""
        yield
        # Clean up sys.modules entries for test modules
        modules_to_remove = [name for name in sys.modules if "test_module_" in name or name == "test_module"]
        for module_name in modules_to_remove:
            del sys.modules[module_name]

    def test_import_file_with_matching_classes(self, tmp_path: Path):
        """Test that file with matching classes is imported."""
        test_file_path = tmp_path / "test_module_with_class.py"
        test_file_path.write_text("""
class StructuredContent:
    pass

class MyContent(StructuredContent):
    value = "imported"
""")
        module = import_module_from_file_if_has_classes(
            str(test_file_path),
            base_class_names=["StructuredContent"],
        )
        assert module is not None
        assert hasattr(module, "MyContent")
        assert module.MyContent.value == "imported"

    def test_skip_file_without_matching_classes(self, tmp_path: Path):
        """Test that file without matching classes is not imported."""
        test_file_path = tmp_path / "test_module_no_match.py"
        # Add code that would execute and cause side effects
        test_file_path.write_text("""
print("This should not execute!")

class UnrelatedClass:
    pass

def some_function():
    pass
""")
        module = import_module_from_file_if_has_classes(
            str(test_file_path),
            base_class_names=["StructuredContent"],
        )
        assert module is None
        # Verify the module was NOT loaded into sys.modules
        assert not any("test_module_no_match" in name for name in sys.modules)

    def test_import_all_files_with_classes_when_no_filter(self, tmp_path: Path):
        """Test that any file with classes is imported when no filter is provided."""
        test_file_path = tmp_path / "test_module_any_class.py"
        test_file_path.write_text("""
class AnyClass:
    value = "any_class"
""")
        module = import_module_from_file_if_has_classes(str(test_file_path))
        assert module is not None
        assert hasattr(module, "AnyClass")
        assert module.AnyClass.value == "any_class"

    def test_skip_file_with_no_classes_when_no_filter(self, tmp_path: Path):
        """Test that file with no classes is skipped even without filter."""
        test_file_path = tmp_path / "test_module_no_classes.py"
        test_file_path.write_text("""
def some_function():
    pass

variable = 42
""")
        module = import_module_from_file_if_has_classes(str(test_file_path))
        assert module is None
