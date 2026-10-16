"""The content-generation leaves' half of the read scope's check.

Every read of a value's URL in the content-generation layer happens while a leaf handles an
assignment, and both orchestration modes call the same leaves — the in-process
``ContentGenerator`` and the Temporal activities — so the leaves are the one place every read and
every hand-off to another reader share. Each leaf authorizes the URLs its assignment declares
(``referenced_uris()``) as its first statement, before the dry-run branch, so a dry run refuses the
method a live run would, and before any worker is built. The document print authorizes first in each
branch instead, its live branch inside the summary event the print ends with, so a print the scope
refuses ends with that event too. See :mod:`pipelex.tools.uri.uri_read_scope` for the rule.

A refusal here is the method's, ``security.method_url_refused``. The run's inputs, the files nested in their lists
and structures included, were checked against the same read scope when the run took them, and refused there as the
caller's (``pipelex.pipeline.input_normalizer``), so a URL a leaf finds out of scope is one the method's own steps
produced: a construct that assembled it, a model's structured output, a function's result.
"""

from mthds.protocol.problem.registry import CoreCode

from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.uri.exceptions import UriReadRefusedError
from pipelex.tools.uri.uri_read_scope import UriReference, authorize_uri_read, authorize_uri_reads


def authorize_assignment_reads(*, job_metadata: JobMetadata, uri_references: list[UriReference]) -> None:
    """Refuse the assignment's reads that the run's read scope does not allow.

    The pipe the assignment belongs to is added to each position, so a refusal names the step.

    Raises:
        UriReadRefusedError: one of the URLs is a storage key outside the read scope, or a local path, refused as the
            method's (``security.method_url_refused``).
    """
    pipe_code = job_metadata.pipe_code
    if pipe_code is not None:
        uri_references = [
            UriReference(uri=uri_reference.uri, position=f"{uri_reference.position} of pipe '{pipe_code}'") for uri_reference in uri_references
        ]
    try:
        authorize_uri_reads(uri_references=uri_references, read_scope=job_metadata.run_metadata.read_scope)
    except UriReadRefusedError as exc:
        exc.with_error_code(CoreCode.SECURITY_METHOD_URL_REFUSED)
        raise


def authorize_method_uri_read(*, uri: str, read_scope: str | None, position: str) -> None:
    """Refuse the read of a URL a document print names that the run's read scope does not allow.

    Raises:
        UriReadRefusedError: the URL is a storage key outside the read scope, or a local path, refused as the method's
            (``security.method_url_refused``).
    """
    try:
        authorize_uri_read(uri=uri, read_scope=read_scope, position=position)
    except UriReadRefusedError as exc:
        exc.with_error_code(CoreCode.SECURITY_METHOD_URL_REFUSED)
        raise
