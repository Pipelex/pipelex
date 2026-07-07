import asyncio
import sys
import tempfile
from pathlib import Path

from typing_extensions import override

from pipelex import log
from pipelex.pipe_operators.func.sandbox.exceptions import SandboxExecutionError, SandboxProvisioningError
from pipelex.pipe_operators.func.sandbox.sandbox_transport import SandboxClientProtocol, SandboxRunRequest, SandboxRunResult

_ENTRYPOINT_MODULE = "pipelex.pipe_operators.func.sandbox.sandbox_entrypoint"


class LocalSubprocessSandboxClient(SandboxClientProtocol):
    """Runs the sandbox entrypoint as a local subprocess in this machine's interpreter.

    The local stand-in for the Daytona box: same request/result contract, same entrypoint, but the
    isolation boundary is a child process + a private temp dir instead of a remote container. It
    honors the same design invariant — the customer's code is imported and executed only in the
    child, never in this process. Used for tests and local end-to-end runs; a DaytonaSandboxClient
    swaps in behind the identical protocol for production.
    """

    @override
    async def run(self, *, request: SandboxRunRequest) -> SandboxRunResult:
        with tempfile.TemporaryDirectory(prefix="pipelex_sandbox_") as tmp_dir:
            request_path = Path(tmp_dir) / "request.json"
            result_path = Path(tmp_dir) / "result.json"
            request_path.write_text(request.model_dump_json(), encoding="utf-8")

            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    _ENTRYPOINT_MODULE,
                    str(request_path),
                    str(result_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                msg = f"Could not spawn the sandbox subprocess: {exc}"
                raise SandboxProvisioningError(msg) from exc

            _stdout, stderr = await process.communicate()

            if process.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                msg = f"Sandbox subprocess for pipe '{request.pipe_code}' exited with code {process.returncode}:\n{detail}"
                raise SandboxExecutionError(msg)

            if not result_path.exists():
                msg = f"Sandbox subprocess for pipe '{request.pipe_code}' produced no result file"
                raise SandboxExecutionError(msg)

            log.verbose(f"Sandbox subprocess for pipe '{request.pipe_code}' completed")
            return SandboxRunResult.model_validate_json(result_path.read_text(encoding="utf-8"))
