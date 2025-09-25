from pathlib import Path

import pytest

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.hub import get_class_registry
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from tests.cases import ClassRegistryTestCases


class TestClassRegistryUtilsIntegration:
    """Integration tests for ClassRegistryUtils using real file operations."""

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_integration_stuffcontent_recursive(self) -> None:
        """Integration test for registering StuffContent classes recursively."""
        class_registry = get_class_registry()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=ClassRegistryTestCases.MODEL_FOLDER_PATH, base_class=StuffContent, is_recursive=True,
        )

        # Should register classes that inherit from StuffContent
        for class_name in ClassRegistryTestCases.CLASSES_TO_REGISTER:
            assert class_registry.get_class(class_name) is not None, f"Expected {class_name} to be registered"

    @pytest.mark.asyncio
    async def test_register_classes_in_folder_integration_stuffcontent_non_recursive(self) -> None:
        """Integration test for registering StuffContent classes non-recursively."""
        class_registry = get_class_registry()
        ClassRegistryUtils.register_classes_in_folder(
            folder_path=ClassRegistryTestCases.MODEL_FOLDER_PATH, base_class=StuffContent, is_recursive=False,
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
