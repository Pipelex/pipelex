"""CLI entrypoint that runs ONE transported PipeFunc request in this process.

Invoked as a subprocess INSIDE an isolated sandbox (a Daytona box or a local subprocess): it reads a
serialized ``PipeFuncExecutionRequest``, runs it via the ``direct`` executor's transported path (which
registers the customer's real code from the crate and runs the one function), and writes the
serialized ``PipeFuncExecutionResponse``.

It lives in open ``pipelex`` and imports no sandbox code, so a box needs only ``pipelex`` installed —
the sandbox *client* (box provisioning, upload/download, teardown) is a worker-side concern that stays
in the out-of-tree plugin. This is the module a sandbox client runs as
``python -m pipelex.pipe_operators.func.pipe_func_transported_entrypoint <request_json> <result_json>``.

On any failure the process exits non-zero with a diagnostic on stderr, which the calling sandbox client
turns into a sandbox error.
"""

import asyncio
import sys
from pathlib import Path

from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_execution_transport import PipeFuncExecutionRequest


def main() -> None:
    """argv: <request_json_path> <result_json_path>."""
    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    request = PipeFuncExecutionRequest.model_validate_json(request_path.read_text(encoding="utf-8"))

    # Import here so module import (e.g. for tests) stays cheap and free of boot side effects.
    from pipelex.pipelex import Pipelex  # noqa: PLC0415

    Pipelex.make(needs_inference=False)
    try:
        result = asyncio.run(DirectPipeFuncExecutor().run_pipe_func_transported(request=request))
    finally:
        Pipelex.teardown_if_needed()
    result_path.write_text(result.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
