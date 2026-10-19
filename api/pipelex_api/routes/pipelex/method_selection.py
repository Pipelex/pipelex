"""The method tree a diagnostic request names, read the one way `/validate` and the crate routes share.

`/validate`, `/resolve`, `/codegen` and `/pipe-io` each take a method as a tree: sent in `files`, with the
`dependencies` it carries and the `resources` that join it, or fetched by an address-form `method_ref`. This module reads
either into a `RequestMethod` with the run routes' own machinery (`pipelex_api.method_tree_request`,
`pipelex_api.method_source.fetched_method`), so the four routes accept, refuse and resolve a tree exactly as the run
routes do: the same limits, the same `method.package_invalid` and `request.blobs_missing` refusals, the same fetch, and
the same Python policy, a `.py` file refused with a 501 `pipelex.deployment.custom_code_requires_sandbox` unless the
deployment is sandbox-hosted.

A sent tree's hash entries resolve in the blob store of the request's `read_scope`, else of the caller's own id
(`resolve_blob_scope`), and the tree is recorded in that store only under a `read_scope` the host named: without one, the
fallback scope is the caller's own id, a prefix no host lists or erases, where a diagnostic request must leave nothing.
"""

import asyncio
from typing import NamedTuple

from fastapi import Request

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.bundle_resources import decode_bundle_resources
from pipelex_api.exceptions import CustomCodeOrigin, RunnerRequestError
from pipelex_api.method_source import fetched_method
from pipelex_api.method_tree_request import (
    REQUEST_METHOD_LABEL,
    RequestMethod,
    ensure_method_holds_a_bundle,
    ensure_python_allowed,
    read_request_method,
    record_request_method,
    tree_documents_of,
    with_resources,
)
from pipelex_api.routes.pipelex.pipeline import resolve_blob_scope

# How the refusals of a sent method name it, as the run routes name it.
_SENT_METHOD_LABEL = "This method"


class SelectedMethod(NamedTuple):
    """A method tree a request named, read in full, and how the entry rule's messages name it."""

    request_method: RequestMethod
    method_label: str
    """`REQUEST_METHOD_LABEL` for a tree sent in `files`, the fetched package's quoted address for a `method_ref`."""


async def select_request_method(
    *,
    request: Request,
    method_ref: str | None,
    resources: dict[str, str] | None,
    read_scope: str | None,
) -> SelectedMethod:
    """The method tree the request names: the package a `method_ref` fetches, else the tree sent in `files`.

    The request envelope already refused a body naming neither or both, so a request without a `method_ref` sends
    `files`, read from the raw JSON text of its body (`tree_documents_of`).

    Raises (as problem documents): the refusals of `read_request_method` and `with_resources`, the `method_ref` fetch
    outcomes (`fetched_method`), a 422 `method.package_invalid` whose `reason` is `no_bundle` for a method whose own tree
    holds no `.mthds` file, and the Python policy's refusals (`ensure_python_allowed`): a 501
    `pipelex.deployment.custom_code_requires_sandbox`, or a 422 `pipelex.deployment.python_structures_refused`.

    The Python policy holds for the crate routes too, although they run nothing: on a deployment that is not
    sandbox-hosted, loading the library imports every `.py` of the tree declaring a `StructuredContent` subclass
    (`LibraryManager.load_libraries`), which runs that file's module-level code in this process. Which files those are
    is a static scan's call, so the policy refuses every `.py` there, exactly as a run and `/v1/validate` do.
    """
    if method_ref is not None:
        fetched = await asyncio.to_thread(fetched_method, method_ref)
        package_label = f"Method package {fetched.label}"
        ensure_method_holds_a_bundle(request_method=fetched.request_method, label=package_label)
        ensure_python_allowed(request_method=fetched.request_method, label=package_label, origin=CustomCodeOrigin.PACKAGE)
        return SelectedMethod(request_method=fetched.request_method, method_label=fetched.label)
    blob_store = RunnerBlobStore.make_for_scope(scope=resolve_blob_scope(request, read_scope=read_scope))
    sent_method = await read_request_method(documents=tree_documents_of(body=await request.body()), blob_store=blob_store)
    if sent_method is None:
        # Unreachable: the request envelope already refused a body naming no method.
        msg = "This request sends no method tree in `files` and no `method_ref`."
        raise RunnerRequestError(msg, field="files")
    request_method = with_resources(request_method=sent_method, resources=decode_bundle_resources(resources=resources))
    ensure_method_holds_a_bundle(request_method=request_method, label=_SENT_METHOD_LABEL)
    ensure_python_allowed(request_method=request_method, label=_SENT_METHOD_LABEL, origin=CustomCodeOrigin.BUNDLE)
    if read_scope is not None:
        await record_request_method(request_method=request_method, blob_store=blob_store)
    return SelectedMethod(request_method=request_method, method_label=REQUEST_METHOD_LABEL)
