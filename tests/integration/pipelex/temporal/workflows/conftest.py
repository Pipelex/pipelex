import uuid

import pytest


@pytest.fixture
def workflow_run_id() -> str:
    """Provide a workflow run ID, mirroring the job_metadata fixture pattern."""
    return str(uuid.uuid4())
