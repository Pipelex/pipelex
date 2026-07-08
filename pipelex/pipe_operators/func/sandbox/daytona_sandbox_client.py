from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.pipe_operators.func.sandbox.exceptions import SandboxExecutionError, SandboxProvisioningError
from pipelex.pipe_operators.func.sandbox.sandbox_transport import SandboxClientProtocol, SandboxRunRequest, SandboxRunResult
from pipelex.system.environment import get_optional_env, get_required_env

_ENTRYPOINT_MODULE = "pipelex.pipe_operators.func.sandbox.sandbox_entrypoint"
# Where the request/result JSON live inside the box. A fresh box per call (decision 1), so fixed
# paths are safe — no cross-run collision.
_REMOTE_DIR = "/tmp/pipelex_sandbox"  # noqa: S108 — path inside the isolated box, not this host
_REMOTE_REQUEST = f"{_REMOTE_DIR}/request.json"
_REMOTE_RESULT = f"{_REMOTE_DIR}/result.json"


class DaytonaSandboxClient(SandboxClientProtocol):
    """Runs the sandbox entrypoint inside a fresh Daytona box — the production isolation boundary.

    Same request/result contract and same entrypoint as ``LocalSubprocessSandboxClient``; only the
    isolation boundary differs (a remote container instead of a child process). One box PER CALL
    (decision 1), torn down in a guaranteed ``finally`` (decision 3), network blocked by default —
    a PipeFunc needs no egress, and the box runs in Daytona's infra, never our VPC.

    The box image (``snapshot``) MUST have ``pipelex`` preinstalled: the entrypoint is
    ``python -m pipelex...sandbox_entrypoint``, and egress is blocked so nothing is pip-installed at
    run time. Requires the ``daytona`` extra (``pip install 'pipelex[daytona]'``).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        snapshot: str | None = None,
        block_network: bool = True,
        bootstrap_pip: str | None = None,
        create_timeout: float = 60.0,
        exec_timeout: int = 300,
    ) -> None:
        # Resolve lazily from env so importing this module never requires the credentials to be set.
        self._api_key = api_key
        self._snapshot = snapshot
        self._block_network = block_network
        # No-snapshot dev/fallback: a pip spec installed in the box before the entrypoint runs, for
        # deployments without a pipelex-preinstalled snapshot (decision 13's runtime-install fallback).
        # When set, egress MUST be open for pip, so network blocking is turned off for that box.
        self._bootstrap_pip = bootstrap_pip
        self._create_timeout = create_timeout
        self._exec_timeout = exec_timeout

    def _resolved_bootstrap_pip(self) -> str | None:
        return self._bootstrap_pip or get_optional_env("DAYTONA_BOOTSTRAP_PIP")

    def _resolved_api_key(self) -> str:
        return self._api_key or get_required_env("DAYTONA_API_KEY")

    def _resolved_snapshot(self) -> str | None:
        # None → Daytona's default image (only usable when it already carries pipelex); production
        # sets DAYTONA_SNAPSHOT to the pipelex-preinstalled snapshot.
        return self._snapshot or get_optional_env("DAYTONA_SNAPSHOT")

    def _build_command(self, *, request_remote: str, result_remote: str) -> str:
        """The command run inside the box. Overridable so the transport can be tested with a stub."""
        return f"python -m {_ENTRYPOINT_MODULE} {request_remote} {result_remote}"

    @override
    async def run(self, *, request: SandboxRunRequest) -> SandboxRunResult:
        # Import lazily: pipelex must import fine without the daytona extra installed.
        try:
            from daytona import AsyncDaytona, CreateSandboxFromSnapshotParams, DaytonaConfig  # noqa: PLC0415
        except ImportError as exc:
            msg = "DaytonaSandboxClient requires the 'daytona' extra: pip install 'pipelex[daytona]'"
            raise SandboxProvisioningError(msg) from exc

        bootstrap_pip = self._resolved_bootstrap_pip()
        # pip needs egress, so a bootstrap install forces the network open for that box.
        block_network = self._block_network and not bootstrap_pip
        daytona = AsyncDaytona(DaytonaConfig(api_key=self._resolved_api_key()))
        try:
            sandbox = await self._provision(
                daytona=daytona,
                params=CreateSandboxFromSnapshotParams(
                    snapshot=self._resolved_snapshot(),
                    network_block_all=block_network,
                    ephemeral=True,
                ),
            )
            snapshot_label = self._resolved_snapshot() or "default-image"
            log.info(
                f"Daytona box {sandbox.id} provisioned for pipe '{request.pipe_code}' (snapshot={snapshot_label}, network_blocked={block_network})"
            )
            try:
                return await self._run_in_box(sandbox=sandbox, request=request)
            finally:
                # Guaranteed teardown on success, throw, or cancel (decision 3).
                await daytona.delete(sandbox)
                log.info(f"Daytona box {sandbox.id} torn down for pipe '{request.pipe_code}'")
        finally:
            await daytona.close()

    async def _provision(self, *, daytona: Any, params: Any) -> Any:
        try:
            return await daytona.create(params, timeout=self._create_timeout)
        # The Daytona SDK raises DaytonaError subclasses (auth, quota, timeout, connection) for
        # provisioning failures; treat them all as a retryable infra fault, distinct from customer
        # code failing inside a box (SandboxExecutionError).
        except self._daytona_error_type() as exc:
            msg = f"Could not provision a Daytona box for pipe: {exc}"
            raise SandboxProvisioningError(msg) from exc

    async def _run_in_box(self, *, sandbox: Any, request: SandboxRunRequest) -> SandboxRunResult:
        bootstrap_pip = self._resolved_bootstrap_pip()
        if bootstrap_pip:
            log.info(f"Daytona box {sandbox.id}: bootstrap-installing '{bootstrap_pip}'")
            install = await sandbox.process.exec(f"pip install --quiet {bootstrap_pip}", timeout=self._exec_timeout)
            if install.exit_code != 0:
                detail = (install.result or "").strip()
                msg = f"Bootstrap pip install in the Daytona box failed with code {install.exit_code}:\n{detail}"
                raise SandboxProvisioningError(msg)
        await sandbox.fs.upload_file(request.model_dump_json().encode("utf-8"), _REMOTE_REQUEST)
        response = await sandbox.process.exec(
            self._build_command(request_remote=_REMOTE_REQUEST, result_remote=_REMOTE_RESULT),
            timeout=self._exec_timeout,
        )
        if response.exit_code != 0:
            detail = (response.result or "").strip()
            msg = f"Daytona box for pipe '{request.pipe_code}' exited with code {response.exit_code}:\n{detail}"
            raise SandboxExecutionError(msg)

        result_bytes = await sandbox.fs.download_file(_REMOTE_RESULT)
        if not result_bytes:
            msg = f"Daytona box for pipe '{request.pipe_code}' produced no result file"
            raise SandboxExecutionError(msg)
        log.verbose(f"Daytona box for pipe '{request.pipe_code}' completed")
        return SandboxRunResult.model_validate_json(result_bytes.decode("utf-8"))

    @staticmethod
    def _daytona_error_type() -> type[Exception]:
        from daytona import DaytonaError  # noqa: PLC0415

        return DaytonaError
