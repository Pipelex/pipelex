"""Framework-agnostic document printing leaf, sibling of ``render_generate``.

Single home for "print a composed document and store it": the direct ``ContentGenerator`` calls it inline, and
a Temporal activity would call it on a worker. Printing and storage happen inside the leaf so the file's bytes
never cross a workflow boundary: only the URL-bearing ``DocumentContent`` is returned. The engine that prints is
the worker of the ``doc_gen`` model the assignment names, resolved when the step ran, and it runs in a worker
thread, since engines are synchronous; a file its document names, such as an image, it reads back through the
``RenderResources`` it is handed, under the run's read scope.

Engines run on a thread pool of their own rather than the event loop's default executor, because an engine's
thread waits while the loop reads a file for it, and that read may itself need a default-executor thread (a
local file read, a DNS lookup, a cloud storage call). Were the engines on the default executor, as many
concurrent prints as it has threads would hold every one of them, and each read would wait behind them until
it timed out.
"""

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor

from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.dry_mock import dry_render_document
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.cogt.doc_gen.doc_gen_engine import get_doc_gen_inference_model, require_doc_gen_engine_installed
from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.cogt.doc_gen.render_job import LoadedResource, RenderedDocument, RenderResources
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.runtime_hub import get_report_delegate
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_bytes import load_bytes_and_mime_type_from_any_uri
from pipelex.tools.uri.uri_read_scope import authorize_uri_read

# How long an engine may wait for one file it reads, such as an image fetched over https.
_RESOURCE_LOAD_TIMEOUT_SECONDS = 120
# How many documents print at once; more wait their turn. A print is CPU-bound apart from its reads.
_MAX_CONCURRENT_PRINTS = 4
_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_PRINTS, thread_name_prefix="pipelex-doc-gen")


class RunRenderResources(RenderResources):
    """The `RenderResources` of one print: files read through the run's storage provider, under its read scope.

    An engine runs in a worker thread and reads synchronously, while storage and fetching are async, so each
    read is handed back to the event loop the print was started from, and the engine's thread waits for it.
    """

    def __init__(self, *, storage_provider: StorageProviderAbstract, read_scope: str | None, loop: asyncio.AbstractEventLoop):
        self._storage_provider = storage_provider
        self._read_scope = read_scope
        self._loop = loop
        self._loop_thread_id = threading.get_ident()

    async def _load(self, *, uri: str, position: str) -> LoadedResource:
        authorize_uri_read(uri=uri, read_scope=self._read_scope, position=position)
        loaded = await load_bytes_and_mime_type_from_any_uri(uri, storage_provider=self._storage_provider)
        return LoadedResource(data=loaded.data, mime_type=loaded.mime_type)

    @override
    def load(self, *, uri: str, position: str) -> LoadedResource:
        if threading.get_ident() == self._loop_thread_id:
            msg = "An engine reads its resources from the worker thread it prints in, never from the event loop's own thread."
            raise RuntimeError(msg)
        future = asyncio.run_coroutine_threadsafe(self._load(uri=uri, position=position), self._loop)
        try:
            return future.result(timeout=_RESOURCE_LOAD_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            # Stop the read too, which would otherwise go on running on the loop after the print has failed.
            future.cancel()
            msg = f"Reading {position} took longer than {_RESOURCE_LOAD_TIMEOUT_SECONDS} seconds."
            raise DocGenRenderError(msg) from exc


async def render_document_and_store(
    render_assignment: RenderDocumentAssignment,
    *,
    generated_content_factory: GeneratedContentFactory,
) -> DocumentContent:
    """Print the composed document with its engine, store the file, and return the `DocumentContent` pointing at it.

    The read scope is authorized first, then the DRY branch, which prints and stores nothing, so a dry run
    refuses what a live one would.

    Raises:
        UriReadRefusedError: an image the document names is outside the run's read scope.
        ModelNotFoundError: the assignment's engine is not a model served here.
        DocGenEngineMissingError: the engine is the built-in one or one of the plugin's and is no longer declared here, or
            no installed plugin registers it.
        DocGenRenderError: the engine could not print it, or failed in a way it did not report.
    """
    authorize_assignment_reads(job_metadata=render_assignment.job_metadata, uri_references=render_assignment.referenced_uris())
    if render_assignment.cogt_run_params.run_mode.is_dry:
        return dry_render_document(render_assignment)
    composition = render_assignment.composition
    inference_model = get_doc_gen_inference_model(
        model_handle=render_assignment.doc_gen_setting.model,
        doc_gen_format=composition.format,
        source=composition.source,
        pipe_code=render_assignment.job_metadata.pipe_code,
    )
    require_doc_gen_engine_installed(
        inference_model=inference_model,
        doc_gen_format=composition.format,
        source=composition.source,
        pipe_code=render_assignment.job_metadata.pipe_code,
    )
    worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model, reporting_delegate=get_report_delegate())
    render_job = composition.make_render_job()
    resources = RunRenderResources(
        storage_provider=generated_content_factory.storage_provider,
        read_scope=render_assignment.job_metadata.run_metadata.read_scope,
        loop=asyncio.get_running_loop(),
    )
    # The context is carried into the thread, as `asyncio.to_thread` would, so the engine logs under the run.
    run_context = contextvars.copy_context()

    def _print() -> RenderedDocument:
        return run_context.run(worker.render, job=render_job, resources=resources)

    try:
        rendered = await asyncio.get_running_loop().run_in_executor(_PRINT_EXECUTOR, _print)
    except PipelexError:
        # Already classified: a refused read, or a failure the engine reported as a `DocGenRenderError`.
        raise
    except Exception as exc:
        # Dynamic plugin dispatch: an engine is plugin code whose exceptions cannot be enumerated, and anything
        # else it raises is a failure to print this document.
        msg = f"The engine '{inference_model.name}' could not print '{composition.filename}': {exc}"
        raise DocGenRenderError(msg) from exc
    return await generated_content_factory.make_document_content(
        storage_scope=render_assignment.job_metadata.run_metadata.storage_scope,
        data=rendered.data,
        mime_type=composition.format.mime_type,
        filename=composition.filename,
    )
