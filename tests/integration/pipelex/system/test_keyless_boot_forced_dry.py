"""Pin the keyless-boot contract (eng review D4): force-DRY flag only, generator backend-keyed.

A keyless boot (``needs_inference=False``) must NOT change generator selection — the backend alone
picks inline vs in-workflow, so a keyless Temporal submitter still dispatches activities (and the
leaf mocks inside them — the Tier 17 no-keys arm depends on it). What keyless boot does instead is
set the forced-DRY flag, which ``PipeRunParamsFactory.make_run_params`` — the single writer of
``run_mode`` — consumes by overriding any requested run mode to DRY, covering every execution
entry point (pipeline API, runtime bridge, factory defaults).
"""

from collections.abc import Generator

import pytest

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_content_generator, is_dry_run_forced
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execution_seams import load_libraries_and_activate, prepare_pipe_job
from pipelex.system.runtime import IntegrationMode
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module sets up and tears down per test."""
    yield
    Pipelex.teardown_if_needed()


class TestKeylessBootForcedDry:
    def _boot_keyless(self, *, temporal_enabled: bool) -> None:
        Pipelex.teardown_if_needed()
        Pipelex.make(
            integration_mode=IntegrationMode.PYTEST,
            needs_inference=False,
            temporal_enabled=temporal_enabled,
        )

    @pytest.mark.asyncio
    async def test_keyless_direct_boot_inline_generator_and_forced_dry(self) -> None:
        """Keyless + direct: inline generator, forced-DRY flag set, and a LIVE-requested job prepared as DRY."""
        try:
            self._boot_keyless(temporal_enabled=False)
            assert is_dry_run_forced()
            assert isinstance(get_content_generator(), ContentGenerator)

            # The flag is consumed at the single writer of run_mode: a LIVE-requested job comes out DRY.
            library_id = load_libraries_and_activate([])
            pipe = PipeFactory[PipeSearch].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_keyless_forced_dry",
                blueprint=PipeSearchBlueprint(
                    description="Keyless forced-dry test",
                    output=NativeConceptCode.SEARCH_RESULT,
                    prompt="What is Pipelex?",
                ),
            )
            pipe_job = await prepare_pipe_job(
                pipe=pipe,
                library_id=library_id,
                execution_config=get_config().pipelex.pipeline_execution_config,
                pipe_run_mode=PipeRunMode.LIVE,
                pipeline_run_id="keyless_forced_dry_run",
                user_id="test-user",
            )
            assert pipe_job.pipe_run_params.run_mode.is_dry
        finally:
            Pipelex.teardown_if_needed()

    def test_keyless_temporal_boot_in_workflow_generator_and_forced_dry(self) -> None:
        """Keyless + Temporal-enabled: the in-workflow generator is still selected (backend-keyed, D4)."""
        try:
            self._boot_keyless(temporal_enabled=True)
            assert is_dry_run_forced()
            assert isinstance(get_content_generator(), ContentGeneratorInWorkflow)
        finally:
            Pipelex.teardown_if_needed()

    def test_keyed_boot_does_not_force_dry(self) -> None:
        """Control arm: a normal boot leaves the flag unset."""
        try:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=IntegrationMode.PYTEST)
            assert not is_dry_run_forced()
        finally:
            Pipelex.teardown_if_needed()
