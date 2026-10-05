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
            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=False)

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
            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True)

            expected_files_length = 3
            assert len(files) == expected_files_length
            file_names = [f.name for f in files]
            assert "file1.py" in file_names
            assert "file2.py" in file_names
            assert "file4.py" in file_names

    def test_find_files_empty_directory(self):
        """Test finding files in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=False)
            assert len(files) == 0

    def test_find_files_no_matches(self):
        """Test finding files with no matches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "file1.txt").touch()
            (Path(temp_dir) / "file2.md").touch()

            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=False)
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

            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True, excluded_dirs=[".venv"])

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

            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True, excluded_dirs=[".venv", "node_modules", "__pycache__"])

            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "root.py" in file_names
            assert "normal.py" in file_names
            assert "venv_file.py" not in file_names
            assert "node_file.py" not in file_names
            assert "cache_file.py" not in file_names

    def test_find_files_no_excluded_dirs(self):
        """Test that passing None for excluded_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create files
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True, excluded_dirs=None)

            # Should find all files when no exclusions
            assert len(files) == 2
            file_names = [f.name for f in files]
            assert "file1.py" in file_names
            assert "venv_file.py" in file_names

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
            py_files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True, excluded_dirs=[".venv"])
            assert len(py_files) == 1
            assert py_files[0].name == "script.py"

            # Find only .json files
            json_files = find_files_in_dir(Path(temp_dir), pattern="*.json", is_recursive=True, excluded_dirs=[".venv"])
            assert len(json_files) == 1
            assert json_files[0].name == "data.json"

    def test_find_files_empty_excluded_list(self):
        """Test that passing an empty list for excluded_dirs works correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            (Path(temp_dir) / "file1.py").touch()

            venv_dir = Path(temp_dir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv_file.py").touch()

            files = find_files_in_dir(Path(temp_dir), pattern="*.py", is_recursive=True, excluded_dirs=[])

            # Empty list should behave like None - no exclusions
            assert len(files) == 2

    def test_exclude_using_absolute_path_structures_directory(self):
        """Test excluding structures directory using absolute path (build_structures_cmd use case)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create Python files in library directory
            (temp_path / "concept_a.py").write_text("# concept_a")
            (temp_path / "concept_b.py").write_text("# concept_b")

            # Create structures subdirectory with generated files (should be excluded)
            structures_dir = temp_path / "structures"
            structures_dir.mkdir()
            (structures_dir / "__init__.py").write_text("")
            (structures_dir / "domain_Generated1.py").write_text("# generated")
            (structures_dir / "domain_Generated2.py").write_text("# generated")

            # Exclude structures using its absolute path
            result = find_files_in_dir(
                temp_path,
                pattern="*.py",
                is_recursive=True,
                excluded_dirs=[str(structures_dir.resolve())],
            )

            # Should find only the manually-created files, not generated ones
            assert len(result) == 2
            result_names = [f.name for f in result]
            assert "concept_a.py" in result_names
            assert "concept_b.py" in result_names
            # Verify no files from structures/ are included
            assert not any("structures" in str(f) for f in result)

    def test_exclude_absolute_path_with_trailing_slash(self):
        """Test that absolute path exclusion works with or without trailing slash."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            (temp_path / "main.py").write_text("# main")

            structures_dir = temp_path / "structures"
            structures_dir.mkdir()
            (structures_dir / "gen.py").write_text("# gen")

            # Test with trailing slash
            result_with_slash = find_files_in_dir(
                temp_path,
                pattern="*.py",
                is_recursive=True,
                excluded_dirs=[str(structures_dir.resolve()) + "/"],
            )

            # Test without trailing slash
            result_without_slash = find_files_in_dir(
                temp_path,
                pattern="*.py",
                is_recursive=True,
                excluded_dirs=[str(structures_dir.resolve())],
            )

            # Both should produce same result
            assert len(result_with_slash) == 1
            assert len(result_without_slash) == 1
            assert result_with_slash[0].name == "main.py"
            assert result_without_slash[0].name == "main.py"

    def test_mixed_name_and_absolute_path_exclusions(self):
        """Test mixing directory name and absolute path exclusions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            (temp_path / "main.py").write_text("# main")

            # Exclude by name
            venv_dir = temp_path / ".venv"
            venv_dir.mkdir()
            (venv_dir / "venv.py").write_text("# venv")

            # Exclude by absolute path
            structures_dir = temp_path / "structures"
            structures_dir.mkdir()
            (structures_dir / "gen.py").write_text("# gen")

            # Regular directory
            src_dir = temp_path / "src"
            src_dir.mkdir()
            (src_dir / "code.py").write_text("# code")

            result = find_files_in_dir(
                temp_path,
                pattern="*.py",
                is_recursive=True,
                excluded_dirs=[".venv", str(structures_dir.resolve())],
            )

            assert len(result) == 2
            result_names = [f.name for f in result]
            assert "main.py" in result_names
            assert "code.py" in result_names
            assert "venv.py" not in result_names
            assert "gen.py" not in result_names
