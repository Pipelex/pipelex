"""Framework-agnostic document printing leaf, sibling of ``render_generate``.

Single home for "print a composed document and store it": the direct ``ContentGenerator`` calls it inline, and
a Temporal activity would call it on a worker. Printing and storage happen inside the leaf so the file's bytes
never cross a workflow boundary: only the URL-bearing ``DocumentContent`` is returned. The engine that prints is
the worker of the ``doc_gen`` model the assignment names, resolved when the step ran, and it runs in a worker
thread, since engines are synchronous; a file its document names, such as an image, it reads back through the
``RenderResources`` it is handed, under the run's read scope.

A step printing from a template file names it in its composition by its tree's digest and its tree path, and the
leaf reads it through the method file store, under the run's read scope: this is the activity, where IO is allowed,
and the compose stage, which may run in a workflow, reads no file. An HTML template file is then rendered with the
step's data by the interpreter's template file stage (``pipelex.cogt.doc_gen.template_file_stage``), a dry print
included, so a value the template reads that does not exist fails the dry run as it fails a live one; an office
template file is handed to its engine, and at a dry print to its engine's template checker.

A relative URL of an HTML document, such as an image beside its template, names a file of the template's method tree
(`pipelex.cogt.doc_gen.method_file_urls`): the engine joins it to the job's base URL and reads it through the
`RenderResources` of the print, which resolves it in the tree's listing and reads the file through the method file
store, under the run's read scope, and never from a disk, when it is an image, a stylesheet or a font. The listing is
read the first time the engine asks for such a file, so a document that names none reads nothing more than it did.

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
from typing import TYPE_CHECKING, NamedTuple

from mthds.method_tree.exceptions import MethodTreeRefusedError
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.dry_mock import dry_render_document
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads, authorize_method_uri_read
from pipelex.cogt.doc_gen.doc_gen_engine import get_doc_gen_inference_model, require_doc_gen_engine_installed
from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError, TemplateUrlRefusedError
from pipelex.cogt.doc_gen.method_file_urls import RelativeUrlBase, is_relative_url, template_asset_refusal
from pipelex.cogt.doc_gen.render_job import LoadedResource, RenderedDocument, RenderJob, RenderResources, is_method_file_url
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest
from pipelex.cogt.inference.inference_call_summary import InferenceCallSummary, InferenceOperation
from pipelex.core.method_trees.method_files import TreeListing, read_listed_file, read_method_file, read_tree_listing
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.runtime_hub import get_report_delegate, get_template_file_stage
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.uri_bytes import load_bytes_and_mime_type_from_any_uri

if TYPE_CHECKING:
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

# How long an engine may wait for one file it reads, such as an image fetched over https.
_RESOURCE_LOAD_TIMEOUT_SECONDS = 120
# How many documents print at once; more wait their turn. A print is CPU-bound apart from its reads.
_MAX_CONCURRENT_PRINTS = 4
_PRINT_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_PRINTS, thread_name_prefix="pipelex-doc-gen")


class RunRenderResources(RenderResources):
    """The `RenderResources` of one print: files read through the run's storage provider, under its read scope.

    An engine runs in a worker thread and reads synchronously, while storage and fetching are async, so each
    read is handed back to the event loop the print was started from, and the engine's thread waits for it.

    In an HTML document, a file of the method tree is read through the method file store: a URL the engine joined
    under the job's base URL, and a relative reference the engine hands as written. Both resolve in the tree of the
    document's template (`document.url_base`), are refused when it has none, and are read only when they name an image,
    a stylesheet or a font, so a relative URL of an HTML document never reaches this host's disk, nor a method file a
    run's input could otherwise make the document carry. Any other URL is read as it names, the read scope checked
    first, a root-absolute local path included. A document with no HTML names no file of a method tree.
    """

    def __init__(
        self,
        *,
        storage_provider: StorageProviderAbstract,
        read_scope: str | None,
        loop: asyncio.AbstractEventLoop,
        document: DocumentComposition | None = None,
    ):
        self._storage_provider = storage_provider
        self._read_scope = read_scope
        self._loop = loop
        self._loop_thread_id = threading.get_ident()
        self._source = document.source if document is not None else None
        self._prints_html = document is not None and document.source.is_html
        self._url_base = document.url_base if document is not None else None
        # The listing of the template's method tree, read the first time the engine asks for one of its files.
        self._tree_listing: TreeListing | None = None
        self._tree_listing_lock = asyncio.Lock()

    async def _load(self, *, uri: str, position: str) -> LoadedResource:
        if self._prints_html and (is_method_file_url(url=uri) or is_relative_url(url=uri)):
            return await self._load_method_file(uri=uri, position=position)
        if is_method_file_url(url=uri):
            source_desc = f"printed {self._source.desc}" if self._source is not None else "with no HTML"
            msg = (
                f"Refused to read {position}. Its URL names a file of a method, which only the relative URLs of an HTML "
                f"template can name, and this document is {source_desc}."
            )
            raise TemplateUrlRefusedError(msg, refusal_code=None)
        authorize_method_uri_read(uri=uri, read_scope=self._read_scope, position=position)
        loaded = await load_bytes_and_mime_type_from_any_uri(uri, storage_provider=self._storage_provider)
        return LoadedResource(data=loaded.data, mime_type=loaded.mime_type)

    async def _load_method_file(self, *, uri: str, position: str) -> LoadedResource:
        """Read the file of the document's method tree `uri` names, through the method file store under the run's read scope.

        Raises:
            TemplateUrlRefusedError: the document's template belongs to no method tree, `uri` names no file of it, or
                the file is not an image, a stylesheet or a font.
            MethodFileUnavailableError: the method file store does not hold the tree or the file for this run.
        """
        url_base = self._url_base
        if url_base is None:
            msg = (
                f"Refused to read {position}. A relative URL names a file of the method the document's template belongs to, "
                "and this template belongs to no method's folder, such as an inline template of a bundle loaded from a string. "
                "Load the method from its folder, or name the file by an https:// or a data: URL."
            )
            raise TemplateUrlRefusedError(msg, refusal_code=None)
        listing = await self._read_tree_listing(url_base=url_base)
        try:
            tree_path = url_base.tree_path_of(url=uri, tree_paths=listing.files.keys())
        except MethodTreeRefusedError as exc:
            msg = f"Refused to read {position}. {exc.message}"
            raise TemplateUrlRefusedError(msg, refusal_code=exc.refusal.code) from exc
        if tree_path is None:
            msg = f"The URL of {position} was taken for a relative URL of the document, and it resolves as none."
            raise PipelexUnexpectedError(msg)
        asset_refusal = template_asset_refusal(tree_path=tree_path)
        if asset_refusal is not None:
            msg = f"Refused to read {position}. {asset_refusal}"
            raise TemplateUrlRefusedError(msg, refusal_code=None)
        data = await read_listed_file(listing=listing, tree_path=tree_path, read_scope=self._read_scope)
        # A method tree records no media type, so the engine types the file itself, as it does a local file's.
        return LoadedResource(data=data, mime_type=None)

    async def _read_tree_listing(self, *, url_base: RelativeUrlBase) -> TreeListing:
        """The listing of the template's method tree, read once per print, whatever number of files the engine asks for."""
        async with self._tree_listing_lock:
            if self._tree_listing is None:
                self._tree_listing = await read_tree_listing(tree_digest=url_base.tree_digest, read_scope=self._read_scope)
            return self._tree_listing

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
            raise DocGenRenderError(msg).with_error_code(PipelexErrorCode.DOCGEN_PRINT_TIMEOUT) from exc


async def render_document_and_store(
    render_assignment: RenderDocumentAssignment,
    *,
    generated_content_factory: GeneratedContentFactory,
) -> DocumentContent:
    """Print the composed document with its engine, store the file, and return the `DocumentContent` pointing at it.

    The read scope is authorized first in either mode, so a dry run, which prints and stores nothing, refuses what
    a live one would. A dry run reads and checks the template file the step prints from, if any, as `_check_template_file`
    says. A live print ends with the event every inference call ends with, as `_print_document` says.

    Raises:
        UriReadRefusedError: an image the document names is outside the run's read scope.
        TemplateUrlRefusedError: a relative URL of an HTML document names no image, stylesheet or font of its template's
            method tree, or the template belongs to no method tree.
        MethodFileUnavailableError: the template file, or a file a relative URL names, cannot be read through the method
            file store for this run.
        ModelNotFoundError: the assignment's engine is not a model served here.
        DocGenEngineMissingError: the engine is the built-in one or one of the plugin's and is no longer declared here, or
            no installed plugin registers it.
        DocGenRenderError: the engine could not print it, or failed in a way it did not report.
    """
    if render_assignment.cogt_run_params.run_mode.is_dry:
        authorize_assignment_reads(job_metadata=render_assignment.job_metadata, uri_references=render_assignment.referenced_uris())
        await _check_template_file(render_assignment=render_assignment)
        return dry_render_document(render_assignment)
    rendered = await _print_document(render_assignment=render_assignment, storage_provider=generated_content_factory.storage_provider)
    composition = render_assignment.composition
    return await generated_content_factory.make_document_content(
        storage_scope=render_assignment.job_metadata.run_metadata.storage_scope,
        data=rendered.data,
        mime_type=composition.format.mime_type,
        filename=composition.filename,
    )


class TemplateFileForPrint(NamedTuple):
    """What the print hands its engine from the step's template file: an HTML one rendered, or an office one's bytes."""

    html: str | None
    template: bytes | None


async def read_template_file(*, render_assignment: RenderDocumentAssignment) -> TemplateFileForPrint:
    """Read the step's template file through the method file store, and render it when it is an HTML template.

    Raises:
        MethodFileUnavailableError: the file cannot be read through the method file store for this run.
        DocGenRenderError: an HTML template file is not UTF-8 text.
    """
    composition = render_assignment.composition
    template_file = composition.template_file
    if template_file is None:
        return TemplateFileForPrint(html=None, template=None)
    data = await read_method_file(file_ref=template_file.file, read_scope=render_assignment.job_metadata.run_metadata.read_scope)
    if template_file.render_context is None:
        return TemplateFileForPrint(html=None, template=data)
    try:
        template_source = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"The template file '{template_file.name}' of '{composition.filename}' is not UTF-8 text."
        raise (
            DocGenRenderError(msg)
            .with_error_code(PipelexErrorCode.DOCGEN_TEMPLATE_INVALID)
            .with_params(template=template_file.name, reason="unreadable", finding="the file is not UTF-8 text")
        ) from exc
    html = await get_template_file_stage().render_html_template_file(template_file=template_file, template_source=template_source)
    return TemplateFileForPrint(html=html, template=None)


async def _check_template_file(*, render_assignment: RenderDocumentAssignment) -> None:
    """At a dry print, read the step's template file and check it against the step's mock inputs.

    An HTML template file is rendered with them, so a value it reads that does not exist fails the step. An office one
    is handed to its engine's template checker, when the engine has one, and the interpreter's template file stage
    reports what it found: an error fails the step, and a warning joins the validation verdict's warnings, or the log.

    Raises:
        MethodFileUnavailableError: the file cannot be read through the method file store for this run.
        PipeDocGenTemplateCheckError: the checker reported errors (raised by the template file stage).
    """
    composition = render_assignment.composition
    template_file = composition.template_file
    if template_file is None:
        return
    read_template = await read_template_file(render_assignment=render_assignment)
    if read_template.template is None:
        return
    inference_model = get_doc_gen_inference_model(
        model_handle=render_assignment.doc_gen_setting.model,
        doc_gen_format=composition.format,
        source=composition.source,
        pipe_code=render_assignment.job_metadata.pipe_code,
    )
    worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model, reporting_delegate=get_report_delegate())
    request = TemplateCheckRequest(
        format=composition.format,
        template=read_template.template,
        template_name=template_file.name,
        inputs=template_file.input_shapes,
        data=composition.data,
    )
    findings = await asyncio.to_thread(worker.check_template, request=request)
    get_template_file_stage().report_template_findings(template_file=template_file, findings=findings)


def _render_job_of(*, composition: DocumentComposition, read_template: TemplateFileForPrint) -> RenderJob:
    return composition.make_render_job(html=read_template.html, template=read_template.template)


async def _print_document(*, render_assignment: RenderDocumentAssignment, storage_provider: StorageProviderAbstract) -> RenderedDocument:
    """Print the composed document with its engine, ending the print with the event every inference call ends with.

    The event is entered before the checks that may refuse the print, the read scope, the engine's model and its
    installation, so a refused print ends with it too, as a refused call of any other family does. It is logged on
    this coroutine rather than on the engine's thread, so its outcome is the awaiting coroutine's: a print cancelled
    from outside ends `cancelled`, once, while the thread, which nothing can stop, finishes its render and logs
    nothing more. An engine reports no usage, so the event carries no tokens and no cost, never a zero standing for
    either.

    Raises:
        UriReadRefusedError: an image the document names is outside the run's read scope.
        TemplateUrlRefusedError: a relative URL of an HTML document names no image, stylesheet or font of its template's
            method tree, or the template belongs to no method tree.
        MethodFileUnavailableError: the template file, or a file a relative URL names, cannot be read through the method
            file store for this run.
        ModelNotFoundError: the assignment's engine is not a model served here.
        DocGenEngineMissingError: the engine is the built-in one or one of the plugin's and is no longer declared here, or
            no installed plugin registers it.
        DocGenRenderError: the engine could not print it, or failed in a way it did not report.
    """
    composition = render_assignment.composition
    model_handle = render_assignment.doc_gen_setting.model
    pipe_code = render_assignment.job_metadata.pipe_code
    # The event reads it when the print ends, so it names the model the handle resolved to, or the handle alone when
    # the print ended before it was resolved or because it resolved to none.
    inference_model: InferenceModelSpec | None = None
    with InferenceCallSummary(
        operation=InferenceOperation.DOC_GEN,
        model_handle=model_handle,
        read_inference_model=lambda: inference_model,
        read_tokens_usage=None,
    ):
        authorize_assignment_reads(job_metadata=render_assignment.job_metadata, uri_references=render_assignment.referenced_uris())
        inference_model = get_doc_gen_inference_model(
            model_handle=model_handle,
            doc_gen_format=composition.format,
            source=composition.source,
            pipe_code=pipe_code,
        )
        require_doc_gen_engine_installed(
            inference_model=inference_model,
            doc_gen_format=composition.format,
            source=composition.source,
            pipe_code=pipe_code,
        )
        engine_name = inference_model.name
        worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model, reporting_delegate=get_report_delegate())
        render_job = _render_job_of(composition=composition, read_template=await read_template_file(render_assignment=render_assignment))
        resources = RunRenderResources(
            storage_provider=storage_provider,
            read_scope=render_assignment.job_metadata.run_metadata.read_scope,
            loop=asyncio.get_running_loop(),
            document=composition,
        )
        # The context is carried into the thread, as `asyncio.to_thread` would, so the engine logs under the run.
        run_context = contextvars.copy_context()

        def _render() -> RenderedDocument:
            return run_context.run(worker.render, job=render_job, resources=resources)

        try:
            return await asyncio.get_running_loop().run_in_executor(_PRINT_EXECUTOR, _render)
        except PipelexError:
            # Already classified: a refused read, or a failure the engine reported as a `DocGenRenderError`.
            raise
        except Exception as exc:
            # Dynamic plugin dispatch: an engine is plugin code whose exceptions cannot be enumerated, and anything
            # else it raises is a failure to print this document.
            msg = f"The engine '{engine_name}' could not print '{composition.filename}': {exc}"
            raise DocGenRenderError(msg) from exc
