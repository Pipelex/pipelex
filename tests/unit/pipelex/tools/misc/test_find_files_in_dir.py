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

    def test_find_files_with_excluded_dirs_single(self):
        """Test finding files with a single excluded directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create excluded directory
            excluded_dir = Path(temp_dir) / ".venv"
            excluded_dir.mkdir()
            (excluded_dir / "excluded.py").touch()

            # Create nested structure in excluded dir
            nested_excluded = excluded_dir / "lib" / "python3.11"
            nested_excluded.mkdir(parents=True)
            (nested_excluded / "nested_excluded.py").touch()

            # Create normal subdirectory
            normal_dir = Path(temp_dir) / "src"
            normal_dir.mkdir()
            (normal_dir / "normal.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[".venv"])

            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "root.py" in file_names
            assert "normal.py" in file_names
            assert "excluded.py" not in file_names
            assert "nested_excluded.py" not in file_names

    def test_find_files_with_excluded_dirs_multiple(self):
        """Test finding files with multiple excluded directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create multiple excluded directories
            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            node_modules = Path(temp_dir) / "node_modules"
            node_modules.mkdir()
            (node_modules / "node_file.py").touch()

            pycache = Path(temp_dir) / "src" / "__pycache__"
            pycache.mkdir(parents=True)
            (pycache / "cache_file.py").touch()

            # Create normal subdirectory
            src_dir = Path(temp_dir) / "src"
            (src_dir / "normal.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[".venv", "node_modules", "__pycache__"])

            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "root.py" in file_names
            assert "normal.py" in file_names
            assert "venv_file.py" not in file_names
            assert "node_file.py" not in file_names
            assert "cache_file.py" not in file_names

    def test_find_files_with_exception_dirs_full_path(self):
        """Test finding files with exception directories using full paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create excluded directory structure
            venv_dir = Path(temp_dir) / ".venv"
            venv_lib = venv_dir / "lib" / "python3.11" / "site-packages"
            venv_lib.mkdir(parents=True)
            (venv_lib / "excluded.py").touch()

            # Create exception directory within excluded
            exception_dir = venv_lib / "pipelex"
            exception_dir.mkdir()
            (exception_dir / "important.py").touch()

            # Create nested file in exception dir
            exception_nested = exception_dir / "builder"
            exception_nested.mkdir()
            (exception_nested / "builder.py").touch()

            # Create another file in venv but outside exception
            other_venv = venv_lib / "other_package"
            other_venv.mkdir()
            (other_venv / "other.py").touch()

            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv"],
                exception_dirs=[str(exception_dir)],
            )

            file_names = [f.name for f in files]
            file_paths_str = [str(f) for f in files]

            # Should include root and exception files, but not other venv files
            assert len(files) == 3
            assert "root.py" in file_names
            assert "important.py" in file_names
            assert "builder.py" in file_names
            assert "excluded.py" not in file_names
            assert "other.py" not in file_names

            # Verify the full paths are correct
            assert any(str(exception_dir / "important.py") in path for path in file_paths_str)
            assert any(str(exception_nested / "builder.py") in path for path in file_paths_str)

    def test_find_files_with_exception_dirs_directory_name(self):
        """Test finding files with exception directories using directory names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create excluded directory structure
            venv_dir = Path(temp_dir) / ".venv"
            venv_lib = venv_dir / "lib"
            venv_lib.mkdir(parents=True)
            (venv_lib / "excluded.py").touch()

            # Create exception directory by name within excluded
            pipelex_dir = venv_lib / "pipelex"
            pipelex_dir.mkdir()
            (pipelex_dir / "important.py").touch()

            # Create another pipelex directory elsewhere to test name matching
            src_pipelex = Path(temp_dir) / "src" / "pipelex"
            src_pipelex.mkdir(parents=True)
            (src_pipelex / "also_important.py").touch()

            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv"],
                exception_dirs=["pipelex"],
            )

            file_names = [f.name for f in files]

            # Should include root, both pipelex directories (one from venv exception, one from src)
            assert len(files) == 3
            assert "root.py" in file_names
            assert "important.py" in file_names
            assert "also_important.py" in file_names
            assert "excluded.py" not in file_names

    def test_find_files_with_exception_dirs_mixed_types(self):
        """Test finding files with exception directories using both full paths and names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create excluded directory structure
            venv_dir = Path(temp_dir) / ".venv"
            venv_packages = venv_dir / "lib" / "site-packages"
            venv_packages.mkdir(parents=True)

            # Exception by full path
            pipelex_dir = venv_packages / "pipelex"
            pipelex_dir.mkdir()
            (pipelex_dir / "pipelex_file.py").touch()

            # Another excluded directory
            node_modules = Path(temp_dir) / "node_modules"
            node_modules.mkdir()
            (node_modules / "node_file.py").touch()

            # Exception by name within node_modules
            special_dir = node_modules / "special"
            special_dir.mkdir()
            (special_dir / "special_file.py").touch()

            # Regular file in node_modules
            (node_modules / "regular_node.py").touch()

            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv", "node_modules"],
                exception_dirs=[str(pipelex_dir), "special"],
            )

            file_names = [f.name for f in files]

            # Should include root, pipelex (full path exception), and special (name exception)
            assert len(files) == 3
            assert "root.py" in file_names
            assert "pipelex_file.py" in file_names
            assert "special_file.py" in file_names
            assert "node_file.py" not in file_names
            assert "regular_node.py" not in file_names

    def test_find_files_with_multiple_exception_dirs_full_paths(self):
        """Test finding files with multiple exception directories using full paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files in root
            (Path(temp_dir) / "root.py").touch()

            # Create excluded directory
            venv_dir = Path(temp_dir) / ".venv"
            packages = venv_dir / "site-packages"
            packages.mkdir(parents=True)

            # First exception directory
            pkg1 = packages / "package1"
            pkg1.mkdir()
            (pkg1 / "pkg1_file.py").touch()

            # Second exception directory
            pkg2 = packages / "package2"
            pkg2.mkdir()
            (pkg2 / "pkg2_file.py").touch()

            # Non-exception directory
            pkg3 = packages / "package3"
            pkg3.mkdir()
            (pkg3 / "pkg3_file.py").touch()

            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv"],
                exception_dirs=[str(pkg1), str(pkg2)],
            )

            file_names = [f.name for f in files]

            assert len(files) == 3
            assert "root.py" in file_names
            assert "pkg1_file.py" in file_names
            assert "pkg2_file.py" in file_names
            assert "pkg3_file.py" not in file_names

    def test_find_files_with_deeply_nested_exception(self):
        """Test finding files with deeply nested exception directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create deeply nested structure
            deep_path = Path(temp_dir) / ".venv" / "lib" / "python3.11" / "site-packages" / "pipelex" / "builder"
            deep_path.mkdir(parents=True)
            (deep_path / "deep_file.py").touch()

            # Create file at intermediate level that should be excluded
            intermediate = Path(temp_dir) / ".venv" / "lib" / "python3.11" / "site-packages"
            (intermediate / "intermediate.py").touch()

            # Create file at root
            (Path(temp_dir) / "root.py").touch()

            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv"],
                exception_dirs=[str(deep_path)],
            )

            file_names = [f.name for f in files]

            assert len(files) == 2
            assert "root.py" in file_names
            assert "deep_file.py" in file_names
            assert "intermediate.py" not in file_names

    def test_find_files_no_excluded_dirs(self):
        """Test that passing None for excluded_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=None)

            # Should find all files when no exclusions
            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "file1.py" in file_names
            assert "venv_file.py" in file_names

    def test_find_files_no_exception_dirs(self):
        """Test that passing None for exception_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[".venv"], exception_dirs=None)

            # Should exclude all venv files when no exceptions
            assert len(files) == 1
            assert files[0].name == "file1.py"

    def test_find_files_exception_not_in_excluded_dir(self):
        """Test that exception directories outside excluded directories are handled correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create normal directory
            src_dir = Path(temp_dir) / "src"
            src_dir.mkdir()
            (src_dir / "src_file.py").touch()

            # Create excluded directory
            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            # Exception directory is in src, not in excluded dir
            files = find_files_in_dir(
                temp_dir,
                "*.py",
                is_recursive=True,
                excluded_dirs=[".venv"],
                exception_dirs=[str(src_dir)],
            )

            # Should find src file (not excluded) but not venv file
            assert len(files) == 1
            assert files[0].name == "src_file.py"

    def test_find_files_pattern_matching(self):
        """Test that file pattern matching works correctly with exclusions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create various file types
            (Path(temp_dir) / "script.py").touch()
            (Path(temp_dir) / "data.json").touch()
            (Path(temp_dir) / "config.toml").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_script.py").touch()
            (venv_dir / "venv_data.json").touch()

            # Find only .py files
            py_files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[".venv"])
            assert len(py_files) == 1
            assert py_files[0].name == "script.py"

            # Find only .json files
            json_files = find_files_in_dir(temp_dir, "*.json", is_recursive=True, excluded_dirs=[".venv"])
            assert len(json_files) == 1
            assert json_files[0].name == "data.json"

    def test_find_files_empty_excluded_list(self):
        """Test that passing an empty list for excluded_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[])

            # Empty list should behave like None - no exclusions
            assert len(files) == 2

    def test_find_files_empty_exception_list(self):
        """Test that passing an empty list for exception_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(temp_dir, "*.py", is_recursive=True, excluded_dirs=[".venv"], exception_dirs=[])

            # Empty exception list should exclude all venv files
            assert len(files) == 1
            assert files[0].name == "file1.py"
