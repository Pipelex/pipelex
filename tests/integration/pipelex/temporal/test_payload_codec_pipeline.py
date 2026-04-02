"""Integration tests for StoragePayloadCodec with real Pipelex pipe execution.

Validates that the codec is transparent to real pipe workflows — WorkingMemory
survives encode→storage→decode across workflow/activity hops when payloads are
offloaded to external storage. Tests single-step, multi-step, and dynamic concept
pipelines through the full WfPipeRouter path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, AsyncGenerator, ClassVar

import pytest
import pytest_asyncio
from temporalio.testing import WorkflowEnvironment

from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.temporal.storage_payload_codec import StoragePayloadCodec
from pipelex.temporal.tasks import Tasks
from pipelex.temporal.temporal_data_converter import make_data_converter
from pipelex.temporal.temporal_hub import get_task_manager, temporal_hub
from pipelex.temporal.temporal_task_manager import TemporalTaskManager
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import assert_stuff_names, assert_text_stuff_names, execute_workflow
from tests.integration.pipelex.temporal.test_data import (
    LargePayloadTestData,
    PayloadCodecPipelineTestData,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from temporalio.client import Client as TemporalClient

    from pipelex.pipe_run.pipe_job import PipeJob

# ---------------------------------------------------------------------------
# Override autouse fixtures from parent conftest — this test module manages
# its own codec-enabled WorkflowEnvironment while still using the full
# TemporalTaskManager infrastructure for real pipe execution.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Initialize Pipelex for logging/config."""
    Pipelex.make(
        integration_mode=IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST,
    )
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(scope="module", autouse=True)
def boot_temporal(reset_pipelex_config_fixture: None) -> Generator[None, None, None]:  # noqa: ARG001
    """Boot the Temporal layer with pipe routers and content generator."""
    manager = TemporalTaskManager()
    temporal_hub.set_task_manager(manager)
    manager.complement_catalog(
        extra_catalog=Tasks.TASK_PACKS,
        extra_workflows=[],
        extra_activities=[],
    )
    manager.setup()

    from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory  # noqa: PLC0415
    from pipelex.hub import get_pipelex_hub, get_storage_provider  # noqa: PLC0415
    from pipelex.temporal.tprl_content_generation.content_generator_child_factory import ContentGeneratorChildFactory  # noqa: PLC0415
    from pipelex.temporal.tprl_pipe.pipe_router_child import make_tprl_pipe_router_child  # noqa: PLC0415
    from pipelex.temporal.tprl_pipe.pipe_router_top import make_tprl_pipe_router_top  # noqa: PLC0415

    pipelex_hub = get_pipelex_hub()
    pipelex_hub.set_pipe_router_top(make_tprl_pipe_router_top())
    pipelex_hub.set_pipe_router(make_tprl_pipe_router_child())

    generated_content_factory = GeneratedContentFactory(storage_provider=get_storage_provider())
    content_generator_child = ContentGeneratorChildFactory.make_content_generator_child(
        generated_content_factory=generated_content_factory,
    )
    pipelex_hub.set_content_generator(content_generator_child)

    yield
    manager.teardown()
    temporal_hub.reset()

    from pipelex.hub import get_inference_manager, get_plugin_manager  # noqa: PLC0415

    get_inference_manager().teardown()
    get_plugin_manager().plugin_sdk_registry.teardown()


# ---------------------------------------------------------------------------
# Codec-enabled WorkflowEnvironment
# ---------------------------------------------------------------------------


class CodecEnvData:
    SIZE_THRESHOLD: ClassVar[int] = PayloadCodecPipelineTestData.SIZE_THRESHOLD
    STORAGE_PREFIX: ClassVar[str] = PayloadCodecPipelineTestData.STORAGE_PREFIX


@pytest_asyncio.fixture(scope="class")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def codec_env(tmp_path_factory: pytest.TempPathFactory) -> AsyncGenerator[tuple[WorkflowEnvironment, Path], None]:
    """Create a WorkflowEnvironment with StoragePayloadCodec enabled."""
    storage_root: Path = tmp_path_factory.mktemp("payload-codec-pipeline")
    storage_provider = LocalStorageProvider(root_path=storage_root)
    codec = StoragePayloadCodec(
        storage_provider=storage_provider,
        size_threshold=CodecEnvData.SIZE_THRESHOLD,
        storage_prefix=CodecEnvData.STORAGE_PREFIX,
    )
    converter = make_data_converter(payload_codec=codec)
    async with await WorkflowEnvironment.start_local(data_converter=converter) as env:  # pyright: ignore[reportUnknownMemberType]
        yield env, storage_root


# ---------------------------------------------------------------------------
# Pipe job fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def native_pipe_job() -> Generator[PipeJob, None, None]:
    """PipeJob for the native text sequence (2-step, no dynamic concepts)."""
    yield from pipe_job_from_bundle(
        bundle_file=PayloadCodecPipelineTestData.NATIVE_BUNDLE_FILE,
        pipe_code=PayloadCodecPipelineTestData.NATIVE_PIPE_CODE,
    )


@pytest.fixture(scope="class")
def dynamic_pipe_job() -> Generator[PipeJob, None, None]:
    """PipeJob for the dynamic concept sequence (Greeting concept created at runtime)."""
    yield from pipe_job_from_bundle(
        bundle_file=PayloadCodecPipelineTestData.DYNAMIC_BUNDLE_FILE,
        pipe_code=PayloadCodecPipelineTestData.DYNAMIC_PIPE_CODE,
    )


@pytest.fixture(scope="class")
def large_payload_pipe_job() -> Generator[PipeJob, None, None]:
    """PipeJob for the large payload stress test (3-step verbose sequence)."""
    yield from pipe_job_from_bundle(
        bundle_file=LargePayloadTestData.BUNDLE_FILE,
        pipe_code=LargePayloadTestData.PIPE_CODE,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_stored_files(storage_root: Path) -> int:
    """Count files in the storage root (excluding directories)."""
    return len([path for path in storage_root.rglob("*") if path.is_file()])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestPayloadCodecPipeline:
    """Real pipe execution through Temporal with StoragePayloadCodec enabled."""

    async def test_native_sequence_with_codec(
        self,
        codec_env: tuple[WorkflowEnvironment, Path],
        native_pipe_job: PipeJob,
    ) -> None:
        """A 2-step PipeSequence with native Text concepts round-trips through the codec."""
        env, storage_root = codec_env
        temporal_client: TemporalClient = env.client
        task_queue = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output = await execute_workflow(native_pipe_job, temporal_client, task_queue)

        assert_text_stuff_names(pipe_output, PayloadCodecPipelineTestData.NATIVE_EXPECTED_STUFF_NAMES)
        assert _count_stored_files(storage_root) > 0, "Codec should have offloaded payloads to storage"

    async def test_dynamic_concept_with_codec(
        self,
        codec_env: tuple[WorkflowEnvironment, Path],
        dynamic_pipe_job: PipeJob,
    ) -> None:
        """Dynamic concept (Greeting) + codec: the most demanding combination."""
        env, storage_root = codec_env
        temporal_client: TemporalClient = env.client
        task_queue = str(uuid.uuid4())
        files_before = _count_stored_files(storage_root)

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output = await execute_workflow(dynamic_pipe_job, temporal_client, task_queue)

        assert_stuff_names(pipe_output, PayloadCodecPipelineTestData.DYNAMIC_EXPECTED_STUFF_NAMES)
        assert _count_stored_files(storage_root) > files_before, "Codec should have stored additional payloads for dynamic concept pipeline"

    async def test_large_payload_multi_step_with_codec(
        self,
        codec_env: tuple[WorkflowEnvironment, Path],
        large_payload_pipe_job: PipeJob,
    ) -> None:
        """3-step pipeline accumulating verbose output — codec stress test."""
        env, storage_root = codec_env
        temporal_client: TemporalClient = env.client
        task_queue = str(uuid.uuid4())
        files_before = _count_stored_files(storage_root)

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output = await execute_workflow(large_payload_pipe_job, temporal_client, task_queue)

        assert_text_stuff_names(pipe_output, LargePayloadTestData.EXPECTED_STUFF_NAMES)
        assert _count_stored_files(storage_root) > files_before, "Codec should have stored payloads for large multi-step pipeline"
