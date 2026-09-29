"""Framework-agnostic document printing leaf, sibling of ``render_generate``.

Single home for "print a composed document and store it": the direct ``ContentGenerator`` calls it inline, and
a Temporal activity would call it on a worker. Printing and storage happen inside the leaf so the file's bytes
never cross a workflow boundary: only the URL-bearing ``DocumentContent`` is returned. The engine that prints is
looked up in the document renderer registry by the composition's format and source, and it runs in a worker
thread, since engines are synchronous; a file its document names, such as an image, it reads back through the
``RenderResources`` it is handed, under the run's read scope.
"""

import asyncio
import threading

from typing_extensions import override

from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.dry_mock import dry_render_document
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.cogt.doc_gen.exceptions import DocGenEngineMissingError, DocGenRenderError
from pipelex.cogt.doc_gen.render_job import RenderResources
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.runtime_hub import get_document_renderer_registry
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri
from pipelex.tools.uri.uri_read_scope import authorize_uri_read

# How long an engine may wait for one file it reads, such as an image fetched over https.
_RESOURCE_LOAD_TIMEOUT_SECONDS = 120


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

    async def _load(self, *, uri: str, position: str) -> bytes:
        authorize_uri_read(uri=uri, read_scope=self._read_scope, position=position)
        return await load_bytes_from_any_uri(uri, storage_provider=self._storage_provider)

    @override
    def load(self, *, uri: str, position: str) -> bytes:
        if threading.get_ident() == self._loop_thread_id:
            msg = "An engine reads its resources from the worker thread it prints in, never from the event loop's own thread."
            raise RuntimeError(msg)
        future = asyncio.run_coroutine_threadsafe(self._load(uri=uri, position=position), self._loop)
        return future.result(timeout=_RESOURCE_LOAD_TIMEOUT_SECONDS)


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
        DocGenEngineMissingError: no installed engine prints the composition's format from its source.
        DocGenRenderError: the engine could not print it.
    """
    authorize_assignment_reads(job_metadata=render_assignment.job_metadata, uri_references=render_assignment.referenced_uris())
    if render_assignment.cogt_run_params.run_mode.is_dry:
        return dry_render_document(render_assignment)
    composition = render_assignment.composition
    renderer = get_document_renderer_registry().get_renderer(doc_gen_format=composition.format, source=composition.source)
    if renderer is None:
        raise DocGenEngineMissingError(
            doc_gen_format=composition.format, source=composition.source, pipe_code=render_assignment.job_metadata.pipe_code
        )
    render_job = composition.make_render_job()
    resources = RunRenderResources(
        storage_provider=generated_content_factory.storage_provider,
        read_scope=render_assignment.job_metadata.run_metadata.read_scope,
        loop=asyncio.get_running_loop(),
    )
    try:
        rendered = await asyncio.to_thread(renderer.render, job=render_job, resources=resources)
    except ValueError as exc:
        msg = f"The {composition.format} engine could not print '{composition.filename}': {exc}"
        raise DocGenRenderError(msg) from exc
    return await generated_content_factory.make_document_content(
        storage_scope=render_assignment.job_metadata.run_metadata.storage_scope,
        data=rendered.data,
        mime_type=composition.format.mime_type,
        filename=composition.filename,
    )
