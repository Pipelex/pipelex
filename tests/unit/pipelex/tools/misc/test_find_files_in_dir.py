import tempfile
from pathlib import Path

from pipelex.tools.misc.file_utils import find_files_in_dir


class TestFindFilesInDir:
    def test_find_files_non_recursive(self):
        """Test finding files non-recursively."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files
            (Path(temp_dir) / "file1.py").touch()
            (Path(temp_dir) / "file2.py").touch()
            (Path(temp_dir) / "file3.txt").touch()

            # Create subdirectory with files
            sub_dir = Path(temp_dir) / "subdir"
            sub_dir.mkdir()
            (sub_dir / "file4.py").touch()

            # Find Python files non-recursively
            files = find_files_in_dir(temp_dir, "*.py", is_recursive=False)

            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "file1.py" in file_names
            assert "file2.py" in file_names
            assert "file4.py" not in file_names

    def test_find_files_recursive(self):
        """Test finding files recursively."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files
            (Path(temp_dir) / "file1.py").touch()
            (Path(temp_dir) / "file2.py").touch()
            (Path(temp_dir) / "file3.txt").touch()

            # Create subdirectory with files
            sub_dir = Path(temp_dir) / "subdir"
            sub_dir.mkdir()
            (sub_dir / "file4.py").touch()

            # Find Python files recursively
            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True)

            expected_files_length = 3
            assert len(files) == expected_files_length
            file_names = [f.name for f in files]
            assert "file1.py" in file_names
            assert "file2.py" in file_names
            assert "file4.py" in file_names

    def test_find_files_empty_directory(self):
        """Test finding files in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            files = find_files_in_dir(temp_dir, "*.py", is_recursive=False)
            assert len(files) == 0

    def test_find_files_no_matches(self):
        """Test finding files with no matches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "file1.txt").touch()
            (Path(temp_dir) / "file2.md").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=False)
            assert len(files) == 0
