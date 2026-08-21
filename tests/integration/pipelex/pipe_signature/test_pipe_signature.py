from typing import TYPE_CHECKING, Callable

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_current_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError
from pipelex.pipe_signature.pipe_signature import PipeSignature
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.system.job_metadata import JobMetadata, RunMetadata, SpecialPipelineId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import DRY_RUN_USER_ID
from tests.integration.pipelex.pipe_signature.conftest import SIGNATURES_DOMAIN_CODE

if TYPE_CHECKING:
    from pipelex.core.stuffs.text_content import TextContent


def _make_runtime(blueprint: PipeSignatureBlueprint, pipe_code: str = "sig_pipe") -> PipeSignature:
    return PipeFactory[PipeSignature].make_from_blueprint(
        domain_code=SIGNATURES_DOMAIN_CODE,
        pipe_code=pipe_code,
        blueprint=blueprint,
        concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
    )


class TestPipeSignature:
    def test_factory_produces_runtime_from_blueprint(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint)
        assert isinstance(runtime, PipeSignature)
        # A signature is outside the executable taxonomy: `type` keeps the "PipeSignature" tag while
        # `pipe_category` is None (no `PipeType`/`PipeCategory` membership).
        assert runtime.type == "PipeSignature"
        assert runtime.pipe_category is None

    def test_is_signature_true(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint)
        assert runtime.is_signature is True
        assert runtime.is_controller is False

    def test_needed_inputs_returns_declared(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint)
        needed = runtime.needed_inputs()
        assert set(needed.variables) == {"doc"}
        assert needed.root["doc"].concept.code == "SigTestDoc"

    def test_required_variables_returns_input_names(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint)
        assert runtime.required_variables() == {"doc"}

    @pytest.mark.asyncio
    async def test_dry_run_produces_mock_text(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="Text")
        runtime = _make_runtime(blueprint, pipe_code="sig_for_text")
        results = await BundleValidator().validate_pipes([runtime], library_id=get_current_library(), allow_signatures=True)
        assert results[runtime.pipe_ref].status is DryRunStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_dry_run_produces_mock_variable_list(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="Text[]")
        runtime = _make_runtime(blueprint, pipe_code="sig_for_text_list")
        needed = WorkingMemoryFactory.convert_to_working_memory_format(needed_inputs_spec=runtime.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed)
        await runtime.run_pipe(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", user_id=DRY_RUN_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)
            ),
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )
        main_stuff = working_memory.get_main_stuff()
        assert isinstance(main_stuff.content, ListContent)

    @pytest.mark.asyncio
    async def test_dry_run_produces_mock_fixed_list(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="Text[3]")
        runtime = _make_runtime(blueprint, pipe_code="sig_for_fixed_list")
        needed = WorkingMemoryFactory.convert_to_working_memory_format(needed_inputs_spec=runtime.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed)
        await runtime.run_pipe(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", user_id=DRY_RUN_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED)
            ),
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )
        main_stuff = working_memory.get_main_stuff()
        assert isinstance(main_stuff.content, ListContent)
        list_content: ListContent[TextContent] = main_stuff.content  # type: ignore[assignment]
        assert len(list_content.items) == 3

    @pytest.mark.asyncio
    async def test_live_run_raises_signature_error(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint, pipe_code="sig_live_fail")
        working_memory = WorkingMemoryFactory.make_empty()
        with pytest.raises(PipeSignatureNotExecutableError) as exc_info:
            await runtime._live_run_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
                job_metadata=JobMetadata(
                    run_metadata=RunMetadata(storage_scope="test/scope", user_id=DRY_RUN_USER_ID, pipeline_run_id=SpecialPipelineId.UNTITLED)
                ),
                working_memory=working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )
        assert runtime.pipe_ref in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_live_run_via_run_pipe_raises_signature_error_with_missing_inputs(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        # run_pipe runs validate_before_run (which checks for missing inputs) before
        # dispatching to live execution. A signature must still surface the actionable
        # PipeSignatureNotExecutableError, not a misleading "missing required inputs".
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint, pipe_code="sig_live_run_pipe_fail")
        working_memory = WorkingMemoryFactory.make_empty()
        with pytest.raises(PipeSignatureNotExecutableError) as exc_info:
            await runtime.run_pipe(
                job_metadata=JobMetadata(
                    run_metadata=RunMetadata(storage_scope="test/scope", user_id=DRY_RUN_USER_ID, pipeline_run_id=SpecialPipelineId.UNTITLED)
                ),
                working_memory=working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )
        assert runtime.pipe_ref in str(exc_info.value)

    def test_input_multiplicity_in_blueprint(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"docs": "SigTestDoc[]"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint, pipe_code="sig_multi_inputs")
        assert runtime.inputs.root["docs"].multiplicity is True

    def test_validators_are_noops(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint, pipe_code="sig_noop_validators")
        runtime.validate_inputs_static()
        runtime.validate_inputs_with_library()
        runtime.validate_output_static()
        runtime.validate_output_with_library()
