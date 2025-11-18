import os
from pathlib import Path

from pipelex.tools.typing.module_inspector import (
    convert_file_path_to_module_path,
)


class TestConvertFilePathToModulePath:
    def test_simple_relative_path(self):
        """Test conversion of a simple relative path."""
        result = convert_file_path_to_module_path("test_module.py")
        # Should convert to absolute path and replace separators with underscores
        assert result.endswith("test_module")
        assert ".py" not in result
        assert result.replace("_", "").replace(os.sep, "").isalnum()

    def test_absolute_path(self, tmp_path: Path):
        """Test conversion of an absolute path."""
        file_path = str(tmp_path / "test_file.py")
        result = convert_file_path_to_module_path(file_path)
        # Should contain the temp path components with separators replaced
        assert "test_file" in result
        assert ".py" not in result
        assert "/" not in result
        assert "\\" not in result

    def test_nested_path(self, tmp_path: Path):
        """Test conversion of a nested path."""
        file_path = str(tmp_path / "subdir" / "nested" / "module.py")
        result = convert_file_path_to_module_path(file_path)
        assert "module" in result
        assert "subdir" in result
        assert "nested" in result
        assert ".py" not in result
        assert "/" not in result
        assert "\\" not in result

    def test_removes_py_extension(self):
        """Test that .py extension is removed."""
        result = convert_file_path_to_module_path("my_module.py")
        assert not result.endswith(".py")
        assert not result.endswith("_py")

    def test_replaces_special_characters(self):
        """Test that special characters are replaced with underscores."""
        result = convert_file_path_to_module_path("my-special.module.py")
        # Hyphens and dots should be replaced with underscores
        assert "-" not in result
        # The .py extension is removed, but other dots become underscores
        assert result.count(".") == 0 or all(c.isalnum() or c == "_" for c in result)

    def test_replaces_spaces(self):
        """Test that spaces are replaced with underscores."""
        result = convert_file_path_to_module_path("my module.py")
        assert " " not in result
        assert "my" in result
        assert "module" in result

    def test_path_with_multiple_special_chars(self):
        """Test path with various special characters."""
        result = convert_file_path_to_module_path("my-file@name#test.py")
        # All special characters should be replaced with underscores
        assert "@" not in result
        assert "#" not in result
        assert "-" not in result
        assert "." not in result
        # Result should be valid Python identifier (alphanumeric + underscores)
        assert all(c.isalnum() or c == "_" for c in result)

    def test_number_at_start_adds_underscore(self):
        """Test that a path starting with a number gets underscore prefix."""
        result = convert_file_path_to_module_path("123_module.py")
        # Module names cannot start with numbers in Python
        assert result[0] == "_" or not result[0].isdigit()
        # If it was prefixed, check that the original number is still there
        if result[0] == "_":
            assert "123" in result

    def test_consistent_results_for_same_path(self):
        """Test that the same path produces the same result."""
        path = "test/module.py"
        result1 = convert_file_path_to_module_path(path)
        result2 = convert_file_path_to_module_path(path)
        assert result1 == result2

    def test_different_paths_produce_different_results(self, tmp_path: Path):
        """Test that different absolute paths produce different results."""
        path1 = str(tmp_path / "module1.py")
        path2 = str(tmp_path / "module2.py")
        result1 = convert_file_path_to_module_path(path1)
        result2 = convert_file_path_to_module_path(path2)
        assert result1 != result2

    def test_uses_absolute_path(self, tmp_path: Path):
        """Test that the function converts to absolute path."""
        # Create a temporary directory and file
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        original_cwd = os.getcwd()
        try:
            # Change to test directory
            os.chdir(test_dir)
            # Use relative path
            result = convert_file_path_to_module_path("relative_module.py")
            # Result should contain the absolute path components
            assert str(test_dir).replace(os.sep, "_") in result or "testdir" in result
        finally:
            # Restore original directory
            os.chdir(original_cwd)

    def test_path_with_dots_in_directory(self):
        """Test path with dots in directory names."""
        result = convert_file_path_to_module_path("dir.name/module.py")
        # Dots should be replaced with underscores
        assert "." not in result
        assert all(c.isalnum() or c == "_" for c in result)

    def test_unicode_characters(self):
        """Test path with Unicode characters."""
        result = convert_file_path_to_module_path("modülé.py")
        # Unicode alphanumeric should be preserved
        assert ".py" not in result
        # Result should only contain valid identifier characters
        assert all(c.isalnum() or c == "_" for c in result)

    def test_minimal_path(self):
        """Test that even minimal paths like '.py' produce valid identifiers."""
        # Even a path like ".py" will be converted to absolute path first,
        # so it will include the current directory components
        result = convert_file_path_to_module_path(".py")
        # Should still be a valid identifier
        assert len(result) > 0
        assert result[0].isalpha() or result[0] == "_"
        assert all(c.isalnum() or c == "_" for c in result)

    def test_result_is_valid_python_identifier(self):
        """Test that the result is always a valid Python identifier."""
        test_paths = [
            "simple.py",
            "path/to/module.py",
            "my-module.py",
            "my_module_123.py",
            "123module.py",
            "special@chars#here.py",
        ]
        for path in test_paths:
            result = convert_file_path_to_module_path(path)
            # Check it's a valid identifier: starts with letter or underscore,
            # followed by letters, digits, or underscores
            assert result[0].isalpha() or result[0] == "_"
            assert all(c.isalnum() or c == "_" for c in result)

    def test_long_path(self, tmp_path: Path):
        """Test conversion of a very long path."""
        # Create a deeply nested path
        long_path = tmp_path
        for i in range(10):
            long_path = long_path / f"dir{i}"
        file_path = str(long_path / "module.py")
        result = convert_file_path_to_module_path(file_path)
        # Should contain elements from all directory levels
        assert "dir0" in result
        assert "dir9" in result
        assert "module" in result
        assert ".py" not in result

    def test_path_with_multiple_dots(self):
        """Test path with multiple dots in filename."""
        result = convert_file_path_to_module_path("my.module.test.py")
        # All dots except in .py extension should become underscores
        assert ".py" not in result
        assert "my" in result
        assert "module" in result
        assert "test" in result

    def test_windows_style_path(self):
        """Test Windows-style path with backslashes."""
        # Use a path that looks like Windows path
        result = convert_file_path_to_module_path("C:\\Users\\test\\module.py")
        # Backslashes should be replaced
        assert "\\" not in result
        assert ":" not in result  # Colon from C: should be replaced
        assert all(c.isalnum() or c == "_" for c in result)

    def test_preserves_uniqueness(self, tmp_path: Path):
        """Test that different paths with similar names produce unique results."""
        path1 = str(tmp_path / "dir1" / "module.py")
        path2 = str(tmp_path / "dir2" / "module.py")
        result1 = convert_file_path_to_module_path(path1)
        result2 = convert_file_path_to_module_path(path2)
        # Even though they have the same filename, full paths should differ
        assert result1 != result2
        assert "dir1" in result1
        assert "dir2" in result2
