"""Pin the keyless-boot contract (eng review D4): force-DRY flag only, generator backend-keyed.

A keyless boot (``needs_inference=False``) must NOT change generator selection — the backend alone
picks inline vs in-workflow, so a keyless Temporal submitter still dispatches activities (and the
leaf mocks inside them — the Tier 17 no-keys arm depends on it). What keyless boot does instead is
set the forced-DRY flag, which ``runtime_hub.resolve_run_mode_for_boot`` applies by overriding any
requested run mode to DRY.

Both run-params factories call it, and both arms are pinned below, because "covers every execution
entry point" is a claim about the set of factories rather than about one of them: the pipe tier's
``PipeRunParamsFactory.make_run_params`` (pipeline API, runtime bridge, factory defaults) and the
kernel tier's ``PipelexKernel.make``, which mints its own ``CogtRunParams`` for a programmatic caller
driving kernel ops with no method loaded. The kernel arm is the one that would silently spend real
money if the rule were applied at the pipe factory alone — its default is ``PipeRunMode.LIVE``, and
a keyless boot is exactly the boot ``pipelex/kernel/`` documents as its target.
"""

from collections.abc import Generator

import pytest

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execution_seams import load_libraries_and_activate, prepare_pipe_job
from pipelex.runtime_hub import get_content_generator, is_dry_run_forced
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.runtime import IntegrationMode, runtime_manager


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module sets up and tears down per test."""
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    """CI mode on CI runners (no terms acceptance), PYTEST locally — mirrors the global conftest boot."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestKeylessBootForcedDry:
    def _boot_keyless(self) -> None:
        Pipelex.teardown_if_needed()
        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
        )

    @pytest.mark.asyncio
    async def test_keyless_direct_boot_inline_generator_and_forced_dry(self) -> None:
        """Keyless + direct: inline generator, forced-DRY flag set, and a LIVE-requested job prepared as DRY."""
        try:
            self._boot_keyless()
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
                execution_config=get_config().interpreter.pipeline_execution,
                pipe_run_mode=PipeRunMode.LIVE,
                pipeline_run_id="keyless_forced_dry_run",
                user_id="test-user",
            )
            assert pipe_job.pipe_run_params.run_mode.is_dry
        finally:
            Pipelex.teardown_if_needed()

    def test_keyless_boot_forces_dry_on_the_kernel_factory_too(self) -> None:
        """The kernel tier's run-params factory honours the same flag — and its default is LIVE.

        Asserted on the default rather than on an explicit ``run_mode=LIVE`` because the default is
        the reachable hazard: a programmatic caller writes ``PipelexKernel.make(user_id=...)``,
        names no mode, and without the coercion gets a LIVE ``CogtRunParams`` that walks straight
        past the leaf's DRY branch into a real provider call.
        """
        try:
            self._boot_keyless()
            assert is_dry_run_forced()

            kernel = PipelexKernel.make(user_id="test-user")

            assert kernel.cogt_run_params.run_mode.is_dry
        finally:
            Pipelex.teardown_if_needed()

    def test_keyless_boot_does_not_legalise_mock_usage_on_a_live_request(self) -> None:
        """The DRY-only sub-flag is validated against the REQUESTED mode, before the coercion.

        Same rule and same ordering as ``PipeRunParamsFactory.make_run_params``. Without it, the one
        illegal combination would raise on a keyed boot and pass silently on a keyless one — a
        contract violation whose visibility depended on whether the process happened to hold keys.
        """
        try:
            self._boot_keyless()
            assert is_dry_run_forced()

            with pytest.raises(ValueError, match="is_mock_usage"):
                PipelexKernel.make(run_mode=PipeRunMode.LIVE, user_id="test-user", is_mock_usage=True)
        finally:
            Pipelex.teardown_if_needed()

    def test_keyed_boot_does_not_force_dry(self) -> None:
        """Control arm: a normal boot leaves the flag unset."""
        try:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
            assert not is_dry_run_forced()
        finally:
            Pipelex.teardown_if_needed()
