"""The content-generation leaves' half of the read scope's check.

Every read of a value's URL in the content-generation layer happens while a leaf handles an
assignment, and both orchestration modes call the same leaves — the in-process
``ContentGenerator`` and the Temporal activities — so the leaves are the one place every read and
every hand-off to another reader share. Each leaf authorizes the URLs its assignment declares
(``referenced_uris()``) as its first statement, before the dry-run branch, so a dry run refuses the
method a live run would, and before any worker is built. See :mod:`pipelex.tools.uri.uri_read_scope`
for the rule.
"""

from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.uri.uri_read_scope import UriReference, authorize_uri_reads


def authorize_assignment_reads(*, job_metadata: JobMetadata, uri_references: list[UriReference]) -> None:
    """Refuse the assignment's reads that the run's read scope does not allow.

    The pipe the assignment belongs to is added to each position, so a refusal names the step.

    Raises:
        UriReadRefusedError: one of the URLs is a storage key outside the read scope, or a local path.
    """
    pipe_code = job_metadata.pipe_code
    if pipe_code is not None:
        uri_references = [
            UriReference(uri=uri_reference.uri, position=f"{uri_reference.position} of pipe '{pipe_code}'") for uri_reference in uri_references
        ]
    authorize_uri_reads(uri_references=uri_references, read_scope=job_metadata.run_metadata.read_scope)
