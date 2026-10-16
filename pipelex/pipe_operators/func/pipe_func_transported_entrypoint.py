"""CLI entrypoint that runs ONE transported PipeFunc request in this process.

Invoked as a subprocess INSIDE an isolated sandbox (a Daytona box or a local subprocess): it reads a
serialized ``PipeFuncExecutionRequest``, runs it via the ``direct`` executor's transported path (which
writes the call's files, imports the step's function by its import path from their root, and runs the
one function), and writes the serialized ``PipeFuncExecutionResponse``.

An optional third argument names a directory the sandbox client already unpacked the call's files into,
such as from one archive per call: it becomes the call's import root, and is left in place. Without it,
the files the request carries are written into a temporary directory, removed after the call.

It lives in open ``pipelex`` and imports no sandbox code, so a box needs only ``pipelex`` installed —
the sandbox *client* (box provisioning, upload/download, teardown) is a worker-side concern that stays
in the out-of-tree plugin. This is the module a sandbox client runs as
``python -m pipelex.pipe_operators.func.pipe_func_transported_entrypoint <request_json> <result_json> [<tree_root>]``.

On any failure the process exits non-zero with a diagnostic on stderr, which the calling sandbox client
turns into a sandbox error.
"""

import asyncio
import sys
from pathlib import Path

from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest


def main() -> None:
    """argv: <request_json_path> <result_json_path> [<tree_root>]."""
    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    tree_root = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    request = PipeFuncExecutionRequest.model_validate_json(request_path.read_text(encoding="utf-8"))

    # Import here so module import (e.g. for tests) stays cheap and free of boot side effects.
    from pipelex.pipelex import Pipelex  # ruff: ignore[import-outside-top-level]

    Pipelex.make(needs_inference=False)
    executor = DirectPipeFuncExecutor()
    try:
        if tree_root is None:
            result = asyncio.run(executor.run_pipe_func_transported(request=request))
        else:
            result = asyncio.run(executor.run_pipe_func_transported_at(request=request, tree_root=tree_root))
    finally:
        Pipelex.teardown_if_needed()
    result_path.write_text(result.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
