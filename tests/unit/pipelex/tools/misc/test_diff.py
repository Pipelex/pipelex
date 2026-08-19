import tempfile
import time
from pathlib import Path

from pytest_mock import MockerFixture
from rich.console import Group
from rich.text import Text

from pipelex.tools.misc.diff import diff_dirs, diff_files, has_diff_dirs, make_diff_dirs_pretty


class TestDiff:
    def test_has_diff_dirs_no_differences(self):
        """Test that identical directories return False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            # Create identical files
            (dir1 / "file1.txt").write_text("content")
            (dir2 / "file1.txt").write_text("content")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is False

    def test_has_diff_dirs_file_only_in_left(self):
        """Test that file only in left directory returns True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "only_left.txt").write_text("content")
            (dir1 / "common.txt").write_text("content")
            (dir2 / "common.txt").write_text("content")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is True

    def test_has_diff_dirs_file_only_in_right(self):
        """Test that file only in right directory returns True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir2 / "only_right.txt").write_text("content")
            (dir1 / "common.txt").write_text("content")
            (dir2 / "common.txt").write_text("content")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is True

    def test_has_diff_dirs_different_content(self):
        """Test that files with different content return True."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "file.txt").write_text("content1")
            (dir2 / "file.txt").write_text("content2")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is True

    def test_has_diff_dirs_pattern_excluded_file_only_in_left(self):
        """A left-only file matching an exclude pattern does not count as a difference."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "common.txt").write_text("content")
            (dir2 / "common.txt").write_text("content")
            (dir1 / "common.txt.bak.20260818T084913Z").write_text("pre-migration copy")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is True
            assert has_diff_dirs(dir1=dir1, dir2=dir2, exclude_patterns={"*.bak.*"}) is False

    def test_has_diff_dirs_pattern_exclusion_reaches_subdirectories(self):
        """An exclude pattern applies at every depth of the comparison."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            (dir1 / "sub").mkdir(parents=True)
            (dir2 / "sub").mkdir(parents=True)

            (dir1 / "sub" / "common.txt").write_text("content")
            (dir2 / "sub" / "common.txt").write_text("content")
            (dir1 / "sub" / "common.txt.bak.20260818T084913Z").write_text("pre-migration copy")

            assert has_diff_dirs(dir1=dir1, dir2=dir2, exclude_patterns={"*.bak.*"}) is False

    def test_has_diff_dirs_pattern_leaves_unmatched_file_visible(self):
        """A pattern excludes only what it matches — a neighbouring extra file still differs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "common.txt.bak.20260818T084913Z").write_text("pre-migration copy")
            (dir1 / "common.txt.bak.notes").write_text("a copy the user named")

            assert has_diff_dirs(dir1=dir1, dir2=dir2, exclude_patterns={"*.bak.[0-9]*Z"}) is True

    def test_make_diff_dirs_pretty_omits_pattern_excluded_file(self):
        """The report leaves out what the verdict looked past, so the two cannot contradict."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "common.txt.bak.20260818T084913Z").write_text("pre-migration copy")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2, exclude_patterns={"*.bak.*"})

            assert isinstance(result, Text)
            assert "No differences found" in result.plain

    def test_has_diff_dirs_recursive(self):
        """Test that subdirectory differences are detected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            # Create identical top-level files
            (dir1 / "file.txt").write_text("content")
            (dir2 / "file.txt").write_text("content")

            # Create subdirectories with differences
            (dir1 / "subdir").mkdir()
            (dir2 / "subdir").mkdir()
            (dir1 / "subdir" / "different.txt").write_text("content1")
            (dir2 / "subdir" / "different.txt").write_text("content2")

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is True

    def test_has_diff_dirs_empty_directories(self):
        """Test that two empty directories return False."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            assert has_diff_dirs(dir1=dir1, dir2=dir2) is False

    def test_diff_files_basic(self):
        """Test basic file diff functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / "file1.txt"
            file2 = Path(temp_dir) / "file2.txt"

            file1.write_text("line1\nline2\nline3\n")
            file2.write_text("line1\nmodified\nline3\n")

            diff = diff_files(file1, file2)

            assert "---" in diff
            assert "+++" in diff
            assert "-line2" in diff
            assert "+modified" in diff

    def test_diff_files_identical(self):
        """Test diff of identical files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / "file1.txt"
            file2 = Path(temp_dir) / "file2.txt"

            file1.write_text("same content\n")
            file2.write_text("same content\n")

            diff = diff_files(file1, file2)

            assert diff == ""

    def test_make_diff_dirs_pretty_no_differences(self):
        """Test that identical directories return Text with no differences message."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "file.txt").write_text("content")
            (dir2 / "file.txt").write_text("content")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2)

            assert isinstance(result, Text)
            assert "No differences found" in str(result)

    def test_make_diff_dirs_pretty_with_differences(self):
        """Test that directories with differences return Group."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "only_left.txt").write_text("left content")
            (dir2 / "only_right.txt").write_text("right content")
            (dir1 / "different.txt").write_text("content1")
            (dir2 / "different.txt").write_text("content2")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2)

            assert isinstance(result, Group)

    def test_make_diff_dirs_pretty_binary_file(self):
        """Test that binary files are handled gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            # Create binary files with different content
            (dir1 / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
            (dir2 / "binary.bin").write_bytes(b"\x04\x05\x06\x07")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2)

            # Should return Group with binary file note
            assert isinstance(result, Group)

    def test_make_diff_dirs_pretty_recursive(self):
        """Test that subdirectory differences are included."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            # Create subdirectories
            (dir1 / "subdir").mkdir()
            (dir2 / "subdir").mkdir()
            (dir1 / "subdir" / "file.txt").write_text("content1")
            (dir2 / "subdir" / "file.txt").write_text("content2")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2)

            assert isinstance(result, Group)

    def test_make_diff_dirs_pretty_accepts_string_paths(self):
        """Test that string paths are accepted."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "file.txt").write_text("content1")
            (dir2 / "file.txt").write_text("content2")

            # Pass as strings
            result = make_diff_dirs_pretty(dir1=str(dir1), dir2=str(dir2))

            assert isinstance(result, Group)

    def test_diff_dirs_calls_pretty_print(self, mocker: MockerFixture):
        """Test that diff_dirs calls PrettyPrinter.pretty_print."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "file.txt").write_text("content")
            (dir2 / "file.txt").write_text("content")

            mock_pretty_print = mocker.patch("pipelex.tools.misc.diff.PrettyPrinter.pretty_print")

            diff_dirs(dir1, dir2)

            mock_pretty_print.assert_called_once()
            call_kwargs = mock_pretty_print.call_args.kwargs
            assert "content" in call_kwargs
            assert "title" in call_kwargs
            assert str(dir1) in call_kwargs["title"]
            assert str(dir2) in call_kwargs["title"]

    def test_diff_dirs_handles_string_paths(self, mocker: MockerFixture):
        """Test that diff_dirs accepts string paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            mock_pretty_print = mocker.patch("pipelex.tools.misc.diff.PrettyPrinter.pretty_print")

            # Pass as strings
            diff_dirs(str(dir1), str(dir2))

            mock_pretty_print.assert_called_once()

    def test_has_diff_dirs_accepts_string_paths(self):
        """Test that has_diff_dirs accepts string paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "file.txt").write_text("content")
            (dir2 / "file.txt").write_text("content")

            # Pass as strings
            result = has_diff_dirs(dir1=str(dir1), dir2=str(dir2))

            assert result is False

    def test_diff_files_accepts_string_paths(self):
        """Test that diff_files accepts string paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = Path(temp_dir) / "file1.txt"
            file2 = Path(temp_dir) / "file2.txt"

            file1.write_text("content1\n")
            file2.write_text("content2\n")

            # Pass as strings
            diff = diff_files(str(file1), str(file2))

            assert "-content1" in diff
            assert "+content2" in diff

    def test_make_diff_dirs_pretty_shows_update_direction(self):
        """Test that diff output shows which file is newer based on modification time."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir1 = Path(temp_dir) / "dir1"
            dir2 = Path(temp_dir) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            # Create file in dir1
            (dir1 / "file.txt").write_text("content1")
            time.sleep(0.1)  # Ensure different modification times
            # Create file in dir2 (newer)
            (dir2 / "file.txt").write_text("content2")

            result = make_diff_dirs_pretty(dir1=dir1, dir2=dir2)

            # Result should be a Group containing the diff
            assert isinstance(result, Group)

            # Convert to string to check for direction indicator
            result_str = ""
            for item in result.renderables:
                result_str += str(item)

            # Should indicate that right is newer
            assert "→" in result_str or "right is newer" in result_str
