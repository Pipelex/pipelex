from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex.config import get_config
from pipelex.hub import get_class_registry
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.test_extras.temporal_registry_test_models import Person
from tests.integration.pipelex.temporal.test_utils import rprint


@pytest.fixture(autouse=True)
def enable_temporal_config():
    """Enable temporal in config for content_generation tests that go through WorkflowExecutor."""
    config = get_config()
    original_enabled = config.temporal.is_enabled
    config.temporal = config.temporal.model_copy(update={"is_enabled": True})
    yield
    config.temporal = config.temporal.model_copy(update={"is_enabled": original_enabled})


@pytest.fixture(autouse=True)
def register_test_temporal_models():
    # Code to run before each test
    rprint("\n[magenta]Temporal classes registration[/magenta]")
    get_class_registry().register_class(class_type=Person)
    yield
    # Code to run after each test
    rprint("\n[magenta]Temporal classes unregistration[/magenta]")
    get_class_registry().unregister_class(class_type=Person)


@pytest.fixture
def tprl_job_metadata(request: FixtureRequest) -> JobMetadata:
    """Provide a JobMetadata instance.

    Uses the test function name as pipeline_run_id for stable test identification.
    """
    pipeline_run_id = cast("str", request.node.originalname)  # pyright: ignore[reportUnknownMemberType]
    return JobMetadata(
        user_id="test",
        pipeline_run_id=pipeline_run_id,
    )
