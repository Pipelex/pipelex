"""CLI entrypoint that runs ONE transported PipeFunc request in this process.

Invoked as a subprocess INSIDE an isolated sandbox (a Daytona box or a local subprocess): it reads a
serialized ``PipeFuncExecutionRequest``, runs it via the ``direct`` executor's transported path (which
imports the step's function by its import path from the root of the call's files, and runs the one
function), and writes the serialized ``PipeFuncExecutionResponse``.

The third argument names the directory the sandbox client unpacked the call's files into, such as from one
archive per call: it becomes the call's import root, and is left in place. A sandbox reaches no method file
store, so its client reads the files of the tree the request names there (``read_pipe_func_call_files``),
where it runs, and hands them over; the request carries no file's bytes.

It lives in open ``pipelex`` and imports no sandbox code, so a box needs only ``pipelex`` installed —
the sandbox *client* (box provisioning, upload/download, teardown) is a worker-side concern that stays
in the out-of-tree plugin. This is the module a sandbox client runs as
``python -m pipelex.pipe_operators.func.pipe_func_transported_entrypoint <request_json> <result_json> <tree_root>``.

On success the result file holds the ``PipeFuncExecutionResponse`` and the process exits zero. On any failure the
process exits non-zero with a diagnostic on stderr. When the failure is the function's own, the ``direct`` executor's
``PipeFuncRaisedError``, it first writes a ``PipeFuncRaisedReport`` to the result file, the operator's view of the
``pipe.function_raised`` problem, which the calling sandbox client reads back (``read_pipe_func_raised_report``) and
raises as the function's failure; on any other failure, such as the function running past its timeout or the call's
files failing to load, it writes nothing there, and the client turns the exit into a sandbox error of its own.
"""

import asyncio
import sys
from pathlib import Path

from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.exceptions import PipeFuncRaisedError
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest
from pipelex.pipe_operators.func.pipe_func_execution_transport import pipe_func_raised_report


def main() -> None:
    """argv: <request_json_path> <result_json_path> <tree_root>."""
    if len(sys.argv) != 4:
        sys.exit("usage: python -m pipelex.pipe_operators.func.pipe_func_transported_entrypoint <request_json> <result_json> <tree_root>")
    request_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    tree_root = Path(sys.argv[3]).resolve()
    request = PipeFuncExecutionRequest.model_validate_json(request_path.read_text(encoding="utf-8"))

    # Import here so module import (e.g. for tests) stays cheap and free of boot side effects.
    from pipelex.pipelex import Pipelex  # ruff: ignore[import-outside-top-level]

    Pipelex.make(needs_inference=False)
    executor = DirectPipeFuncExecutor()
    try:
        result = asyncio.run(executor.run_pipe_func_transported_at(request=request, tree_root=tree_root))
    except PipeFuncRaisedError as exc:
        # The function's own failure is reported before the process exits non-zero, while Pipelex is still up to build
        # its problem; the error still propagates, so the exit and the diagnostic on stderr are any failure's.
        result_path.write_text(pipe_func_raised_report(error=exc).model_dump_json(), encoding="utf-8")
        raise
    finally:
        Pipelex.teardown_if_needed()
    result_path.write_text(result.model_dump_json(), encoding="utf-8")


if __name__ == "__main__":
    main()
