"""Job metadata the manifold tests hand to a request, and the header value it must produce."""

from typing import ClassVar

from pipelex.system.job_metadata import JobMetadata, RunMetadata


class ManifoldMetadataTestData:
    """A job whose run carries host labels, and the exact `x-pipelex-metadata` value it yields.

    The expected value is written out as the wire string rather than rebuilt from the job, so a
    change to the encoding (key order, separators, escaping) turns a test red instead of moving with it.
    """

    EXTRAS: ClassVar[dict[str, str]] = {"org_id": "org_acme", "api_key_id": "key_123"}

    JOB_METADATA: ClassVar[JobMetadata] = JobMetadata(
        run_metadata=RunMetadata(
            storage_scope="test/scope",
            read_scope=None,
            user_id="user_42",
            pipeline_run_id="run_abc",
            extras={"org_id": "org_acme", "api_key_id": "key_123"},
        ),
        pipe_code="summarize_doc",
        pipe_run_id="0123456789abcdef",
        content_generation_job_id="cgj_1",
    )

    EXPECTED_HEADER_VALUE: ClassVar[str] = (
        '{"org_id":"org_acme","api_key_id":"key_123","user_id":"user_42","pipeline_run_id":"run_abc",'
        '"pipe_run_id":"0123456789abcdef","pipe_code":"summarize_doc","content_generation_job_id":"cgj_1"}'
    )
