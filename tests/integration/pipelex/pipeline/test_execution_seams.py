"""Focused tests for the execution seams ``acquire_library`` / ``prepare_pipe_job``.

These pin the seams as standalone, reusable building blocks (the shape Phase 2's
``BundleValidator`` will compose): ``acquire_library`` loads a bundle into a fresh
library and owns its load-failure teardown; ``prepare_pipe_job`` builds an
equivalent :class:`PipeJob` against an already-open library.
"""

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_required_entry_pipe
from pipelex.pipeline import execution_seams as execution_seams_module
from pipelex.pipeline.execution_seams import acquire_library, prepare_pipe_job
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import DRY_RUN_USER_ID

_SEAMS_DOMAIN = "seams_test"
_SEAMS_MTHDS = f"""
domain = "{_SEAMS_DOMAIN}"
description = "Minimal bundle for execution-seams tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to build a PipeJob"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestExecutionSeams:
    async def test_acquire_library_loads_bundle_and_returns_main_pipe(self) -> None:
        library_manager = get_library_manager()
        library_id = "seams_acquire_ok_lib"
        returned_id, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert returned_id == library_id
            # main_pipe is returned domain-qualified.
            assert qualified_main_pipe is not None
            assert qualified_main_pipe == f"{_SEAMS_DOMAIN}.echo_topic"
            # Library is left open + current; the loaded pipe is resolvable.
            assert get_current_library_id_or_none() == library_id
            assert get_required_entry_pipe(pipe_code=qualified_main_pipe).code == "echo_topic"
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    async def test_acquire_library_tears_down_on_load_failure(self, mocker: MockerFixture) -> None:
        # A failure during the load window (simulated by resolve_library_dirs raising,
        # mirroring the validate_bundle lifecycle tests) must tear the just-opened
        # library down — no leak — and restore the caller's outer current-library
        # (whatever it was, including None) rather than stranding it.
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(
            execution_seams_module,
            "resolve_library_dirs",
            side_effect=TypeError("simulated load failure in acquire_library"),
        )
        teardown_before = teardown_spy.call_count
        prev_library_id = get_current_library_id_or_none()

        with pytest.raises(TypeError):
            acquire_library(library_id="seams_acquire_fail_lib", mthds_contents=[_SEAMS_MTHDS])

        # The just-opened library is torn down exactly once...
        assert teardown_spy.call_count == teardown_before + 1
        assert teardown_spy.call_args_list[-1].kwargs["library_id"] == "seams_acquire_fail_lib"
        # ...and the caller's outer current-library is restored, not left holding the failed one.
        assert get_current_library_id_or_none() == prev_library_id

    async def test_acquire_library_with_empty_id_adopts_generated_id(self) -> None:
        # open_library generates a fresh uuid when given a falsy library_id. acquire_library must
        # return THAT id (not the falsy "" it was passed), so every downstream op targets the real
        # library. A caller passing library_id="" is valid (the signature is `str`), so this must work.
        library_manager = get_library_manager()
        returned_id, qualified_main_pipe = acquire_library(library_id="", mthds_contents=[_SEAMS_MTHDS])
        try:
            # Non-empty: the generated uuid, not the falsy "" that was passed in.
            assert returned_id
            assert qualified_main_pipe is not None
            assert qualified_main_pipe == f"{_SEAMS_DOMAIN}.echo_topic"
            # The returned id is the one left open + current and holding the loaded pipe.
            assert get_current_library_id_or_none() == returned_id
            assert get_required_entry_pipe(pipe_code=qualified_main_pipe).code == "echo_topic"
        finally:
            library_manager.teardown(library_id=returned_id)
            clear_current_library()

    async def test_acquire_library_with_empty_id_tears_down_only_the_opened_library(self, mocker: MockerFixture) -> None:
        # Regression for the teardown-all catastrophe: before the fix, acquire_library kept the falsy
        # passed-in library_id="" and, on a load failure, called teardown(library_id="") — which falls
        # past LibraryManager.teardown's `if library_id:` guard and tears down EVERY open library. With
        # the fix it adopts open_library's generated id and tears down only that one, leaving unrelated
        # open libraries intact.
        library_manager = get_library_manager()
        unrelated_id, _ = library_manager.open_library(library_id="seams_unrelated_lib")
        try:
            open_library_spy = mocker.spy(library_manager, "open_library")
            teardown_spy = mocker.spy(library_manager, "teardown")
            mocker.patch.object(
                execution_seams_module,
                "resolve_library_dirs",
                side_effect=TypeError("simulated load failure in acquire_library"),
            )
            with pytest.raises(TypeError):
                acquire_library(library_id="", mthds_contents=[_SEAMS_MTHDS])

            # teardown targeted the generated id open_library returned, not the falsy "".
            generated_id, _ = open_library_spy.spy_return
            assert generated_id
            assert teardown_spy.call_args_list[-1].kwargs["library_id"] == generated_id
            # The unrelated library survived — teardown("") would have nuked it along with all others.
            assert library_manager.get_library(library_id=unrelated_id) is not None
        finally:
            library_manager.teardown(library_id=unrelated_id)
            clear_current_library()

    async def test_prepare_pipe_job_builds_equivalent_job_against_open_library(self) -> None:
        library_manager = get_library_manager()
        library_id = "seams_prepare_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_entry_pipe(pipe_code=qualified_main_pipe)
            pipe_job = await prepare_pipe_job(
                storage_scope="test/scope",
                user_id="test-user",
                pipe=pipe,
                library_id=library_id,
                execution_config=_dry_mock_config(),
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id="seams-prepare-run-id",
            )
            assert pipe_job.pipe.code == "echo_topic"
            assert pipe_job.pipe_run_params.run_mode.is_dry
            assert pipe_job.job_metadata.pipeline_run_id == "seams-prepare-run-id"
            assert pipe_job.library_crate is not None
            # Mock input materialized for the pipe's needed input.
            assert "subject" in pipe_job.get_working_memory().root
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    @pytest.mark.parametrize(
        "bad_scope",
        [
            pytest.param("../other/run", id="traversal-leading"),
            pytest.param("tenant/../other", id="traversal-interior"),
            pytest.param("/tenant/run", id="leading-slash-absolute-key"),
            pytest.param("", id="empty"),
            pytest.param("tenant/run\n", id="trailing-newline"),
        ],
    )
    async def test_an_unsafe_scope_is_refused_before_anything_is_written(self, mocker: MockerFixture, bad_scope: str) -> None:
        """The validator must run BEFORE the normalizer, not after it.

        `JobMetadata` validates the scope, and that is where the invariant is
        documented — but it was constructed *below* the data-url normalization,
        which writes `{storage_scope}/assets/...` to real storage. So a scope
        carrying `..` escaped the tenant's namespace and the guard meant to stop
        it ran afterwards, on damage already done. The defect was ordering, not
        absence, which is why asserting the raise is not enough: the spy is what
        proves nothing was written on the way to it.
        """
        library_manager = get_library_manager()
        library_id = "seams_scope_guard_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_entry_pipe(pipe_code=qualified_main_pipe)
            normalize_spy = mocker.spy(execution_seams_module, "normalize_data_urls_to_storage")
            normalize_config = (
                get_config()
                .interpreter.pipeline_execution.with_execution_overrides(
                    generate_graph=False,
                    mock_inputs=False,
                )
                .model_copy(update={"is_normalize_data_urls_to_storage": True})
            )

            with pytest.raises(ValueError, match="Invalid storage_scope"):
                await prepare_pipe_job(
                    storage_scope=bad_scope,
                    pipe=pipe,
                    library_id=library_id,
                    execution_config=normalize_config,
                    pipe_run_mode=PipeRunMode.DRY,
                    pipeline_run_id="seams-scope-guard-run-id",
                    user_id=DRY_RUN_USER_ID,
                    # NON-EMPTY on purpose. With `PipelineInputs()` the falsy-inputs
                    # gate skips normalize on its own, so the spy assertion below
                    # would hold no matter where the validator sits — a test that
                    # passes with the guard deleted. Real inputs are what put the
                    # normalizer on the path this test is about.
                    inputs=PipelineInputs(root={"subject": "a topic"}),
                )

            assert normalize_spy.call_count == 0
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()

    async def test_prepare_pipe_job_skips_normalize_for_empty_inputs(self, mocker: MockerFixture) -> None:
        # Pins the falsy-inputs semantics at the normalize gate — the discriminating check the
        # pipeline_run_setup characterization test could not make. With empty PipelineInputs (falsy) +
        # normalize enabled + mock disabled, `if inputs:` leaves working_memory None, so the
        # `if working_memory and is_normalize and not is_mock` gate skips normalize. Under an
        # `inputs is not None` regression, make_from_pipeline_inputs would build an (always-truthy, since
        # WorkingMemory defines no __bool__/__len__) empty WorkingMemory and normalize WOULD run. Asserting
        # the spy never fires catches that regression; the prior root == {} assertion alone did not.
        library_manager = get_library_manager()
        library_id = "seams_normalize_gate_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_entry_pipe(pipe_code=qualified_main_pipe)
            normalize_spy = mocker.spy(execution_seams_module, "normalize_data_urls_to_storage")
            normalize_config = (
                get_config()
                .interpreter.pipeline_execution.with_execution_overrides(
                    generate_graph=False,
                    mock_inputs=False,
                )
                .model_copy(update={"is_normalize_data_urls_to_storage": True})
            )

            pipe_job = await prepare_pipe_job(
                storage_scope="test/scope",
                pipe=pipe,
                library_id=library_id,
                execution_config=normalize_config,
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id="seams-normalize-run-id",
                user_id=DRY_RUN_USER_ID,
                inputs=PipelineInputs(),
            )

            # Empty (falsy) inputs => no working memory built => normalize gate skipped.
            assert normalize_spy.call_count == 0
            assert pipe_job.get_working_memory().root == {}
        finally:
            library_manager.teardown(library_id=library_id)
            clear_current_library()
