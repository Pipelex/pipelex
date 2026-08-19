"""`save_text_to_path` writes LF on every platform, so generated artifacts are byte-identical everywhere."""

from pathlib import Path

from pipelex.tools.misc.file_utils import load_text_from_path, save_text_to_path


class TestSaveTextToPath:
    def test_newlines_are_written_as_lf(self, tmp_path: Path) -> None:
        r"""No `\r` reaches the disk, whatever `os.linesep` says.

        This is a tripwire, not a discriminating test: on POSIX `os.linesep` is already `\n`, so it
        passes with or without the fix. It goes red the day a Windows runner appears, or the day the
        explicit `newline` argument is dropped — which is exactly when the guarantee would break.
        """
        target = tmp_path / "artifact.py"
        save_text_to_path("line one\nline two\n", path=target)
        assert b"\r" not in target.read_bytes()
        assert target.read_bytes() == b"line one\nline two\n"

    def test_carriage_returns_in_the_text_survive_verbatim(self, tmp_path: Path) -> None:
        r"""Text that deliberately carries `\r\n` round-trips byte-for-byte, never doubled to `\r\r\n`.

        With the default translating write, a `\r\n` in the string becomes `\r\r\n` on Windows because
        only the `\n` is translated. Pinning `newline="\n"` disables translation entirely, so the text is
        the file.
        """
        target = tmp_path / "crlf.txt"
        save_text_to_path("first\r\nsecond\r\n", path=target)
        assert target.read_bytes() == b"first\r\nsecond\r\n"

    def test_round_trip_through_the_matching_reader(self, tmp_path: Path) -> None:
        """What `save_text_to_path` writes, `load_text_from_path` reads back unchanged."""
        target = tmp_path / "nested" / "artifact.ts"
        save_text_to_path("export const a = 1;\n", path=target, create_directory=True)
        assert load_text_from_path(target) == "export const a = 1;\n"
