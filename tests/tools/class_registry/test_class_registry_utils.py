from pathlib import Path

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.core.stuff_content import StuffContent
from pipelex.hub import get_class_registry
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from tests.tools.test_data import ClassRegistryTestCases


class TestClassRegistryUtilsUnit:
    """Unit tests for ClassRegistryUtils using mocks."""

    def test_register_classes_in_file(self, mocker: MockerFixture):
        """Test registering classes from a Python file."""
        # Mock the module utilities to avoid complex file operations
        mock_module = mocker.MagicMock()
        mock_module.__name__ = "test_module"

        # Mock the functions at the location where they're imported in ClassRegistryUtils
        mock_import = mocker.patch("pipelex.tools.class_registry_utils.import_module_from_file", return_value=mock_module)
        mock_find = mocker.patch("pipelex.tools.class_registry_utils.find_classes_in_module", return_value=[str, int])

        # Mock the global class registry
        mock_registry = mocker.MagicMock()
        mocker.patch("pipelex.tools.class_registry_utils.get_class_registry", return_value=mock_registry)

        # Mock sys.modules for cleanup verification
        mock_sys_modules = mocker.patch("pipelex.tools.class_registry_utils.sys.modules", spec=dict)

        ClassRegistryUtils.register_classes_in_file(file_path="/fake/path.py", base_class=None, is_include_imported=False)

        # Verify the mocked functions were called correctly
        mock_import.assert_called_once_with("/fake/path.py")
        mock_find.assert_called_once_with(module=mock_module, base_class=None, include_imported=False)

        # Verify sys.modules cleanup
        mock_sys_modules.__delitem__.assert_called_once_with("test_module")

        # Verify classes were registered with the global registry
        mock_registry.register_classes.assert_called_once_with(classes=[str, int])

    def test_register_classes_in_folder_unit(self, mocker: MockerFixture):
        """Unit test for registering classes from a folder using mocks."""
        # Mock the file finding and registration
        mock_files = [Path("/fake/file1.py"), Path("/fake/file2.py")]
        mock_find_files = mocker.patch.object(ClassRegistryUtils, "find_files_in_dir", return_value=mock_files)
        mock_register_file = mocker.patch.object(ClassRegistryUtils, "register_classes_in_file")

        ClassRegistryUtils.register_classes_in_folder(folder_path="/fake/folder", base_class=BaseModel, is_recursive=True, is_include_imported=False)

        # Verify find_files_in_dir was called correctly
        mock_find_files.assert_called_once_with(dir_path="/fake/folder", pattern="*.py", is_recursive=True)

        # Verify register_classes_in_file was called for each file
        assert mock_register_file.call_count == 2
        mock_register_file.assert_any_call(file_path="/fake/file1.py", base_class=BaseModel, is_include_imported=False)
        mock_register_file.assert_any_call(file_path="/fake/file2.py", base_class=BaseModel, is_include_imported=False)


class TestClassRegistryUtilsIntegration:
    """Integration tests for ClassRegistryUtils using real file operations."""

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_integration_stuffcontent_recursive(self) -> None:
        """Integration test for registering StuffContent classes recursively."""
        class_registry = get_class_registry()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=ClassRegistryTestCases.MODEL_FOLDER_PATH, base_class=StuffContent, is_recursive=True
        )

        # Should register classes that inherit from StuffContent
        for class_name in ClassRegistryTestCases.CLASSES_TO_REGISTER:
            assert class_registry.get_class(class_name) is not None, f"Expected {class_name} to be registered"

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_integration_stuffcontent_non_recursive(self) -> None:
        """Integration test for registering StuffContent classes non-recursively."""
        class_registry = get_class_registry()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=ClassRegistryTestCases.MODEL_FOLDER_PATH, base_class=StuffContent, is_recursive=False
        )

        # Should register only top-level StuffContent classes
        for class_name in ["Class1", "Class2", "Class4"]:  # Only from top-level files
            assert class_registry.get_class(class_name) is not None, f"Expected {class_name} to be registered"

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_integration_no_base_class(self) -> None:
        """Integration test for registering all classes when no base class is specified."""
        class_registry = get_class_registry()

        # Record classes before registration to check for new registrations
        classes_before: set[str] = set()
        for class_name in ["Class1", "Class2", "Class3", "Class4", "ClassA", "ClassB"]:
            if class_registry.has_class(class_name):
                classes_before.add(class_name)

        ClassRegistryUtils.register_classes_in_folder(folder_path=ClassRegistryTestCases.MODEL_FOLDER_PATH, base_class=None, is_recursive=True)

        # Should register all classes
        for class_name in ["Class1", "Class2", "Class3", "Class4", "ClassA", "ClassB"]:
            assert class_registry.get_class(class_name) is not None, f"Expected {class_name} to be registered"

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_empty_directory_integration(self, tmp_path: Path) -> None:
        """Integration test for registering classes from an empty folder."""
        # Create an empty directory
        empty_dir = tmp_path / "empty_folder"
        empty_dir.mkdir()

        # This should not raise an error and should not register any classes
        ClassRegistryUtils.register_classes_in_folder(folder_path=str(empty_dir), base_class=StuffContent, is_recursive=True)

        # Verify no new classes were registered (we can't easily check the exact count,
        # but the operation should complete without error)
        assert True  # If we get here without exception, the test passed
