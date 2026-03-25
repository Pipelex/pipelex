import uuid
from collections.abc import Generator

import pytest

from pipelex.hub import get_report_delegate


@pytest.fixture
def workflow_run_id() -> Generator[str, None, None]:
    """Provide a workflow run ID with an open reporting registry.

    Opens a registry for the run ID before the test and closes it after,
    mirroring the job_metadata fixture pattern.
    """
    run_id = str(uuid.uuid4())
    get_report_delegate().open_registry(pipeline_run_id=run_id)
    yield run_id
    get_report_delegate().close_registry(pipeline_run_id=run_id)
