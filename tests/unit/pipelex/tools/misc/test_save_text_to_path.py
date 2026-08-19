"""`save_text_to_path` writes LF on every platform, so generated artifacts are byte-identical everywhere."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.tools.misc.file_utils import load_text_from_path, save_text_to_path

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestSaveTextToPath:
    def test_the_lf_guarantee_is_handed_to_the_writer(self, mocker: MockerFixture, tmp_path: Path) -> None:
        r"""The discriminating test of the pair: it pins the argument, not `os.linesep`'s opinion.

        The byte-level tests below cannot fail on a POSIX runner, and CI is Linux-only — so dropping
        `newline="\n"` would leave every gate green. Asserting the call reaches `write_text` with it is
        platform-independent, so this one goes red the moment the guarantee is removed.
        """
        write_text = mocker.patch.object(Path, "write_text")

        save_text_to_path("line one\n", path=tmp_path / "artifact.py")

        assert write_text.call_args.kwargs.get("newline") == "\n"
        assert write_text.call_args.kwargs.get("encoding") == "utf-8"

    def test_newlines_are_written_as_lf(self, tmp_path: Path) -> None:
        r"""No `\r` reaches the disk, whatever `os.linesep` says.

        A tripwire rather than a discriminating test: on POSIX `os.linesep` is already `\n`, so it passes
        with or without the fix, and it is the test above that actually pins the guarantee. This one
        documents the observable outcome, and goes red on its own the day a Windows runner appears.
        """
        target = tmp_path / "artifact.py"
        save_text_to_path("line one\nline two\n", path=target)
        assert b"\r" not in target.read_bytes()
        assert target.read_bytes() == b"line one\nline two\n"

    def test_carriage_returns_in_the_text_survive_verbatim(self, tmp_path: Path) -> None:
        r"""Text that deliberately carries `\r\n` round-trips byte-for-byte, never doubled to `\r\r\n`.

        With the default translating write, a `\r\n` in the string becomes `\r\r\n` on Windows because
        only the `\n` is translated. Pinning `newline="\n"` disables translation entirely, so the text is
        the file. Also a POSIX tripwire — the call-args test is what pins this on a Linux runner.
        """
        target = tmp_path / "crlf.txt"
        save_text_to_path("first\r\nsecond\r\n", path=target)
        assert target.read_bytes() == b"first\r\nsecond\r\n"

    def test_round_trip_through_the_matching_reader(self, tmp_path: Path) -> None:
        """What `save_text_to_path` writes, `load_text_from_path` reads back unchanged."""
        target = tmp_path / "nested" / "artifact.ts"
        save_text_to_path("export const a = 1;\n", path=target, create_directory=True)
        assert load_text_from_path(target) == "export const a = 1;\n"
