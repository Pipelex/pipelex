"""The pool of worker threads that method loads run in, off the event loop.

A method load is blocking work that can take long: it lists and hashes the method's files, judges its
`requirements.txt` through the package-offer factory of the deployment's PipeFunc sandbox, which may resolve the
requirements, and reads the methods installed on this host or fetches a package a bundle calls by its address. On the
event loop it would hold up every other request or activity the loop serves, so every load pipelex reaches from
asynchronous code runs in this pool, through `run_method_load`, and so does the blocking work around one, such as
writing a request's method tree to disk and removing it, judging its requirements before it loads, and listing a tree to
find its entry pipe. A host that calls a load itself from asynchronous code runs it here the same way.

The pool is bounded: at most `METHOD_LOAD_MAX_THREADS` of these calls run at once in a process, and one asked for while
every thread is busy waits for a thread to free, its caller awaiting on the event loop without blocking it. The bound,
and the pool being this one rather than asyncio's default executor, keep slow loads, each of which can hold its thread
for seconds while a package is fetched or a sandbox resolves requirements, from taking the threads the default executor
lends every other blocking call of the process, such as a DNS lookup, so a burst of them never starves unrelated
requests on a small container.
"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

from pipelex.tools.misc.async_utils import WorkerThreads

_T = TypeVar("_T")
_P = ParamSpec("_P")

#: How many method loads, and calls of the blocking work around them, run at once in a process.
METHOD_LOAD_MAX_THREADS = 4

METHOD_LOAD_THREADS = WorkerThreads(name="pipelex-method-load", max_workers=METHOD_LOAD_MAX_THREADS)


async def run_method_load(func: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs) -> _T:
    """Run a method load, or the blocking work around one, in the method-load pool, off the event loop.

    The call runs in a copy of the caller's context, and a cancellation of the caller goes through only once the call
    has ended, or at once when no thread has taken it yet (`WorkerThreads.run`).
    """
    return await METHOD_LOAD_THREADS.run(func, *args, **kwargs)
