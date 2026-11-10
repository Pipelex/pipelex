import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture, MockType

from pipelex.errors.problem import ProblemView
from pipelex.tools.document_conversion.exceptions import (
    ConversionLimitKind,
    DocumentConverterUnavailableError,
    DocumentTooLargeToConvertError,
    DocumentUnreadableByConverterError,
)
from pipelex.tools.document_conversion.soffice_converter import SOFFICE_CONVERTER_NAME, SofficeConverter

SOFFICE_PATH = Path("/opt/libreoffice/program/soffice")
VERSION_OUTPUT = b"LibreOffice 24.8.4.2 bb3cfa12c7b1bf994ecc5649a80400d06cd71002\n"
PDF_BYTES = b"%PDF-1.7\nthe pdf"
SOURCE_BYTES = b"PK\x03\x04 an office file"
MAX_SOURCE_BYTES = 1_000
PROCESS_PID = 4242

_MODULE = "pipelex.tools.document_conversion.soffice_converter"


class _FakeSoffice:
    """Stands in for `asyncio.create_subprocess_exec`: answers `--version`, and converts as its mode says."""

    def __init__(self, *, mocker: MockerFixture, mode: str) -> None:
        self.mocker = mocker
        # `convert` writes the PDF, `no_pdf` writes nothing, `hang` never finishes.
        self.mode = mode
        self.commands: list[list[str]] = []
        self.conversion_process: MockType | None = None

    async def create_subprocess_exec(self, *command: str, **kwargs: Any) -> MockType:  # ruff: ignore[unused-method-argument]
        self.commands.append(list(command))
        process: MockType = self.mocker.MagicMock()
        process.pid = PROCESS_PID
        process.returncode = 0
        process.wait = self.mocker.AsyncMock(return_value=0)
        if "--version" in command:
            process.communicate = self.mocker.AsyncMock(return_value=(VERSION_OUTPUT, None))
            return process
        self.conversion_process = process
        match self.mode:
            case "convert":
                output_dir = Path(command[command.index("--outdir") + 1])
                (output_dir / "document.pdf").write_bytes(PDF_BYTES)
                process.communicate = self.mocker.AsyncMock(return_value=(b"convert document.docx -> document.pdf\n", None))
            case "no_pdf":
                process.returncode = 1
                process.communicate = self.mocker.AsyncMock(return_value=(b"Error: source file could not be loaded\n", None))
            case _:
                # Still running until killed.
                process.returncode = None

                async def never_finish() -> tuple[bytes, None]:
                    await asyncio.sleep(60)
                    return b"", None

                process.communicate = never_finish
        return process


def _make_converter(*, timeout_seconds: float = 120) -> SofficeConverter:
    return SofficeConverter(binary_path=SOFFICE_PATH, timeout_seconds=timeout_seconds, max_source_bytes=MAX_SOURCE_BYTES)


def _install(*, mocker: MockerFixture, mode: str) -> _FakeSoffice:
    fake_soffice = _FakeSoffice(mocker=mocker, mode=mode)
    mocker.patch(f"{_MODULE}.asyncio.create_subprocess_exec", side_effect=fake_soffice.create_subprocess_exec)
    return fake_soffice


@pytest.mark.asyncio(loop_scope="class")
class TestSofficeConverter:
    async def test_a_conversion_runs_headless_with_a_fresh_profile_and_reads_the_pdf(self, mocker: MockerFixture) -> None:
        fake_soffice = _install(mocker=mocker, mode="convert")
        converter = _make_converter()

        first = await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="DOCX")
        await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="xlsx")

        assert first.pdf_bytes == PDF_BYTES
        assert first.converter_name == SOFFICE_CONVERTER_NAME
        assert first.converter_version == "LibreOffice 24.8.4.2 bb3cfa12c7b1bf994ecc5649a80400d06cd71002"
        version_commands = [command for command in fake_soffice.commands if "--version" in command]
        conversion_commands = [command for command in fake_soffice.commands if "--convert-to" in command]
        assert len(version_commands) == 1
        assert len(conversion_commands) == 2
        command = conversion_commands[0]
        assert command[0] == str(SOFFICE_PATH)
        assert command[1].startswith("-env:UserInstallation=file://")
        assert "--headless" in command
        assert command[command.index("--convert-to") + 1] == "pdf"
        assert Path(command[-1]).name == "document.docx"
        # Each conversion has a profile of its own.
        assert conversion_commands[0][1] != conversion_commands[1][1]

    async def test_no_pdf_produced_is_the_file_unreadable(self, mocker: MockerFixture) -> None:
        _install(mocker=mocker, mode="no_pdf")
        converter = _make_converter()

        with pytest.raises(DocumentUnreadableByConverterError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="pptx")

        problem = exc_info.value.with_input(input_name="deck").to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.INPUT_FILE_UNREADABLE
        assert problem.params is not None
        assert problem.params.as_wire() == {"input": "deck", "file_type": "pptx", "reason": "conversion_failed"}

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows has no process groups to kill; the process alone is killed there")
    async def test_a_conversion_past_its_timeout_kills_the_process_group_and_is_out_of_time(self, mocker: MockerFixture) -> None:
        fake_soffice = _install(mocker=mocker, mode="hang")
        killpg = mocker.patch(f"{_MODULE}.os.killpg")
        converter = _make_converter(timeout_seconds=0.05)

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="xlsx")

        killpg.assert_called_once_with(PROCESS_PID, signal.SIGKILL)
        assert fake_soffice.conversion_process is not None
        fake_soffice.conversion_process.wait.assert_awaited_once()
        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        assert error.limit_kind == ConversionLimitKind.SECONDS
        assert "time limit" in error.message

    async def test_a_source_past_the_limit_is_refused_before_soffice_runs(self, mocker: MockerFixture) -> None:
        fake_soffice = _install(mocker=mocker, mode="convert")
        converter = _make_converter()

        with pytest.raises(DocumentTooLargeToConvertError) as exc_info:
            await converter.convert_to_pdf(data=b"x" * (MAX_SOURCE_BYTES + 1), format_key="docx")

        assert fake_soffice.commands == []
        assert exc_info.value.limit_kind == ConversionLimitKind.BYTES

    async def test_soffice_that_cannot_start_is_the_converter_unavailable(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{_MODULE}.asyncio.create_subprocess_exec", side_effect=FileNotFoundError("no such file"))
        converter = _make_converter()

        with pytest.raises(DocumentConverterUnavailableError) as exc_info:
            await converter.convert_to_pdf(data=SOURCE_BYTES, format_key="odt")
        assert exc_info.value.resolve_error_code() == CoreCode.RUNTIME_UNAVAILABLE

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows has no process groups to kill; the process alone is killed there")
    async def test_a_cancelled_conversion_kills_and_reaps_the_process_group_and_leaves_no_directory(self, mocker: MockerFixture) -> None:
        fake_soffice = _install(mocker=mocker, mode="hang")
        killpg = mocker.patch(f"{_MODULE}.os.killpg")
        converter = _make_converter()

        conversion = asyncio.create_task(converter.convert_to_pdf(data=SOURCE_BYTES, format_key="docx"))
        for _ in range(200):
            if fake_soffice.conversion_process is not None:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.01)
        conversion.cancel()
        with pytest.raises(asyncio.CancelledError):
            await conversion

        killpg.assert_called_once_with(PROCESS_PID, signal.SIGKILL)
        assert fake_soffice.conversion_process is not None
        fake_soffice.conversion_process.wait.assert_awaited_once()
        conversion_command = next(command for command in fake_soffice.commands if "--convert-to" in command)
        work_dir = Path(conversion_command[conversion_command.index("--outdir") + 1]).parent
        assert not work_dir.exists()

    async def test_callers_starting_at_once_ask_soffice_its_version_once(self, mocker: MockerFixture) -> None:
        fake_soffice = _install(mocker=mocker, mode="convert")
        converter = _make_converter()

        versions = await asyncio.gather(*(converter.get_converter_version() for _ in range(5)))

        assert set(versions) == {"LibreOffice 24.8.4.2 bb3cfa12c7b1bf994ecc5649a80400d06cd71002"}
        assert len(fake_soffice.commands) == 1
