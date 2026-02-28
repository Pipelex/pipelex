from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from pytest import FixtureRequest
from temporalio.client import Client as TemporalClient

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.deep_flow.temporal_connect import connect_to_temporal
from pipelex.deep_flow.temporal_manager import TemporalWorkerEnvironment
from pipelex.deep_flow.test_extras.deep_flow_registry_test_models import Person
from pipelex.deep_flow.test_helpers.deep_flow_pytest_plugins import DeepFlowPytestOption
from pipelex.deep_flow.tprl_content_generation.content_generator_child import ContentGeneratorChild
from pipelex.deep_flow.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory
from pipelex.deep_flow.tprl_content_generation.content_generator_top import ContentGeneratorTop
from pipelex.deep_flow.tprl_content_generation.content_generator_top_factory import ContentGeneratorTopFactory
from pipelex.hub import get_class_registry
from tests.integration.pipelex.deep_flow.test_utils import rprint


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
async def top_crafter(request: FixtureRequest, generated_content_factory: GeneratedContentFactory) -> AsyncGenerator[ContentGeneratorTop, None]:  # noqa: RUF029
    # Code to run before each test
    rprint("\n[magenta]TopCrafter setup[/magenta]")
    worker_environment = TemporalWorkerEnvironment(request.config.getoption(DeepFlowPytestOption.WORKER_ENVIRONMENT))
    crafter = ContentGeneratorTopFactory.make_content_generator_top(
        generated_content_factory=generated_content_factory,
        worker_environment=worker_environment,
    )
    # Return it for use in tests
    yield crafter
    # Code to run after each test
    rprint("\n[magenta]TopCrafter teardown[/magenta]")


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def temporal_client() -> AsyncGenerator[TemporalClient, None]:
    # Code to run before each test
    rprint("\n[magenta]TemporalClient setup[/magenta]")
    client = await connect_to_temporal()
    # Return it for use in tests
    yield client
    # Code to run after each test
    rprint("\n[magenta]TemporalClient teardown[/magenta]")


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
