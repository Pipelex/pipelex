from collections.abc import Generator
from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.config import get_config
from pipelex.hub import get_class_registry, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_manager import TemporalWorkerEnvironment
from pipelex.temporal.test_extras.temporal_registry_test_models import Person
from pipelex.temporal.tprl_content_generation.content_generator_child import ContentGeneratorChild
from pipelex.temporal.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory
from pipelex.temporal.tprl_content_generation.content_generator_top import ContentGeneratorTop
from pipelex.temporal.tprl_content_generation.content_generator_top_factory import ContentGeneratorTopFactory
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


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def top_crafter(  # noqa: RUF029
    temporal_client: TemporalClient, generated_content_factory: GeneratedContentFactory
) -> AsyncGenerator[ContentGeneratorTop, None]:
    # Code to run before each test
    rprint("\n[magenta]TopCrafter setup[/magenta]")
    crafter = ContentGeneratorTopFactory.make_content_generator_top(
        generated_content_factory=generated_content_factory,
        worker_environment=TemporalWorkerEnvironment.INTERNAL,
        temporal_client=temporal_client,
    )
    # Return it for use in tests
    yield crafter
    # Code to run after each test
    rprint("\n[magenta]TopCrafter teardown[/magenta]")


@pytest.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
def child_crafter(generated_content_factory: GeneratedContentFactory) -> Generator[ContentGeneratorChild, None, None]:
    # Code to run before each test
    rprint("\n[magenta]ChildCrafter setup[/magenta]")
    crafter = ContentGeneratorChildFactory.make_content_generator_child(
        generated_content_factory=generated_content_factory,
    )
    # Return it for use in tests
    yield crafter
    # Code to run after each test
    rprint("\n[magenta]ChildCrafter teardown[/magenta]")


@pytest.fixture
def tprl_job_metadata(request: FixtureRequest) -> Generator[JobMetadata, None, None]:
    """Provide a JobMetadata instance with an open reporting registry.

    Uses the test function name as pipeline_run_id, matching the convention
    used by TestTprlCrafterTop tests.
    """
    pipeline_run_id = cast("str", request.node.originalname)  # pyright: ignore[reportUnknownMemberType]
    get_report_delegate().open_registry(pipeline_run_id=pipeline_run_id)
    yield JobMetadata(
        user_id="test",
        pipeline_run_id=pipeline_run_id,
    )
    get_report_delegate().close_registry(pipeline_run_id=pipeline_run_id)
