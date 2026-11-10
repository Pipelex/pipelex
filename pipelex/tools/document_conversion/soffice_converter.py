"""The `soffice` backend: LibreOffice run on this machine, once per conversion, in a temporary directory of its own.

It is for a developer's machine and the tests. It is no isolation boundary: `soffice` reads the file with the rights
of the process that runs it, so a server reading other people's files runs Gotenberg in a container of its own, as the
hosted plane does.

Each conversion gets a fresh LibreOffice profile (`-env:UserInstallation=file://<temp dir>`), so two conversions at
once never share the profile lock and nothing one file does to the profile reaches the next. The process runs in a
process group of its own, killed whole at the timeout: `soffice` starts a child that does the work, and killing the
launcher alone would leave it running.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import sys
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from time import monotonic

from typing_extensions import override

from pipelex import log
from pipelex.tools.document_conversion.converter_version_cache import ConverterVersionCache
from pipelex.tools.document_conversion.document_converter_protocol import (
    PDF_MAGIC,
    ConvertedPdf,
    DocumentConverterProtocol,
    is_convertible_format_key,
)
from pipelex.tools.document_conversion.exceptions import (
    ConversionLimitKind,
    DocumentConverterAnswerError,
    DocumentConverterUnavailableError,
    DocumentFormatNotConvertibleError,
    DocumentTooLargeToConvertError,
    DocumentUnreadableByConverterError,
)

SOFFICE_CONVERTER_NAME = "soffice"

# What a source is named in its temporary directory: LibreOffice reads the extension for the format, and the PDF it
# writes takes the source's stem.
_SOURCE_STEM = "document"
# How much of `soffice`'s output a failure quotes in the operator's diagnostics.
_OUTPUT_EXCERPT_CHARS = 500


class SofficeConverter(DocumentConverterProtocol):
    """Converts an Office file with the `soffice` executable at `binary_path`."""

    def __init__(self, *, binary_path: Path, timeout_seconds: float, max_source_bytes: int) -> None:
        """Set up the backend; `soffice` is first run by the first conversion or version request.

        Args:
            binary_path: The `soffice` executable, already found, as an absolute path.
            timeout_seconds: How long one conversion may run before its process group is killed.
            max_source_bytes: The largest file converted; a larger one is refused before anything runs.
        """
        self._binary_path = binary_path
        self._timeout_seconds = timeout_seconds
        self._max_source_bytes = max_source_bytes
        self._version_cache = ConverterVersionCache(known_version=None)

    @property
    @override
    def converter_name(self) -> str:
        return SOFFICE_CONVERTER_NAME

    @property
    def binary_path(self) -> Path:
        """The `soffice` executable this backend runs."""
        return self._binary_path

    @override
    async def get_converter_version(self) -> str:
        return await self._version_cache.get_or_fetch(fetch=self._fetch_version)

    async def _fetch_version(self) -> str:
        """The first line `soffice --version` prints.

        Raises:
            DocumentConverterUnavailableError: `soffice` could not be started, or printed no version.
        """
        async with _temporary_work_dir() as work_dir:
            outcome = await self._run(arguments=["--version"], work_dir=work_dir)
        if outcome is None:
            msg = f"soffice did not print its version within {self._timeout_seconds:.0f} seconds."
            raise DocumentConverterUnavailableError(msg)
        return_code, output = outcome
        version = output.strip().splitlines()[0].strip() if output.strip() else ""
        if return_code != 0 or not version:
            msg = f"soffice did not print its version: exit code {return_code}, output {output[:_OUTPUT_EXCERPT_CHARS]!r}."
            raise DocumentConverterUnavailableError(msg)
        return version

    @override
    async def convert_to_pdf(self, *, data: bytes, format_key: str) -> ConvertedPdf:
        if not is_convertible_format_key(format_key=format_key):
            msg = f"The format '{format_key}' is not one the runtime converts to a PDF."
            raise DocumentFormatNotConvertibleError(msg)
        normalized_format_key = format_key.lower()
        if len(data) > self._max_source_bytes:
            msg = f"The file of {len(data)} bytes is past the converter's limit of {self._max_source_bytes} bytes: it was not converted."
            raise DocumentTooLargeToConvertError(
                msg, format_key=normalized_format_key, limit_kind=ConversionLimitKind.BYTES, limit=self._max_source_bytes, size=len(data)
            )
        converter_version = await self.get_converter_version()

        async with _temporary_work_dir() as work_dir:
            source_path = work_dir / f"{_SOURCE_STEM}.{normalized_format_key}"
            output_dir = work_dir / "out"
            await asyncio.to_thread(_write_source, source_path=source_path, data=data, output_dir=output_dir)
            started = monotonic()
            outcome = await self._run(
                arguments=["--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(output_dir), str(source_path)],
                work_dir=work_dir,
            )
            elapsed = monotonic() - started
            if outcome is None:
                msg = f"The conversion ran past its time limit of {self._timeout_seconds:.0f} seconds: soffice was killed."
                raise DocumentTooLargeToConvertError(
                    msg,
                    format_key=normalized_format_key,
                    limit_kind=ConversionLimitKind.SECONDS,
                    limit=round(self._timeout_seconds),
                    size=round(elapsed),
                )
            return_code, output = outcome
            pdf_bytes = await asyncio.to_thread(_read_pdf_if_written, pdf_path=output_dir / f"{_SOURCE_STEM}.pdf")
        if pdf_bytes is None:
            msg = f"soffice produced no PDF: exit code {return_code}, output {output[:_OUTPUT_EXCERPT_CHARS]!r}."
            raise DocumentUnreadableByConverterError(msg, format_key=normalized_format_key)
        if not pdf_bytes.startswith(PDF_MAGIC):
            msg = f"soffice wrote {len(pdf_bytes)} bytes that are not a PDF."
            raise DocumentConverterAnswerError(msg)
        log.debug(f"Converted a {normalized_format_key} file with soffice in {elapsed:.1f} seconds")
        return ConvertedPdf(pdf_bytes=pdf_bytes, converter_name=SOFFICE_CONVERTER_NAME, converter_version=converter_version)

    async def _run(self, *, arguments: list[str], work_dir: Path) -> tuple[int, str] | None:
        """Run `soffice` with a fresh profile under `work_dir`, its exit code and output, or None when it was killed.

        The process group is killed and reaped whenever the run ends with the process still alive: at the timeout, and
        when the task awaiting it is cancelled or anything else interrupts it, so no LibreOffice outlives its caller.

        Raises:
            DocumentConverterUnavailableError: The executable could not be started.
        """
        profile_url = (work_dir / "profile").as_uri()
        command = [str(self._binary_path), f"-env:UserInstallation={profile_url}", *arguments]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=work_dir,
                # A process group of its own, so the timeout kills the child doing the work too.
                start_new_session=True,
            )
        except OSError as exc:
            msg = f"soffice could not be started: {type(exc).__name__}."
            raise DocumentConverterUnavailableError(msg) from exc
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except TimeoutError:
            return None
        finally:
            if process.returncode is None:
                _kill_process_group(process=process)
                # Shielded, so a second cancellation does not leave the killed process unreaped.
                await asyncio.shield(process.wait())
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        return_code = process.returncode if process.returncode is not None else -1
        return return_code, output


@contextlib.asynccontextmanager
async def _temporary_work_dir() -> AsyncGenerator[Path, None]:
    """A temporary directory of one conversion, made and removed in a worker thread, removed however the work ends."""
    work_dir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="pipelex-soffice-"))
    try:
        yield work_dir
    finally:
        # Shielded, so a cancelled conversion still leaves no directory behind.
        await asyncio.shield(asyncio.to_thread(shutil.rmtree, work_dir, ignore_errors=True))


def _write_source(*, source_path: Path, data: bytes, output_dir: Path) -> None:
    """Write the file to convert and make the directory `soffice` writes its PDF to."""
    source_path.write_bytes(data)
    output_dir.mkdir()


def _read_pdf_if_written(*, pdf_path: Path) -> bytes | None:
    """The PDF `soffice` wrote, or None when it wrote none."""
    if not pdf_path.is_file():
        return None
    return pdf_path.read_bytes()


def _kill_process_group(*, process: asyncio.subprocess.Process) -> None:
    """Kill the process and every process it started, in the process group `start_new_session` gave it."""
    if sys.platform == "win32":
        process.kill()
        return
    # The group is gone already when the process ended between the timeout and here.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
