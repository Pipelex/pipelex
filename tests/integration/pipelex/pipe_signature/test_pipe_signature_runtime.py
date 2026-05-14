from typing import TYPE_CHECKING, Callable

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_blueprint import PipeCategory, PipeType
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.pipe_run.dry_run import DryRunStatus, convert_to_working_memory_format, dry_run_pipe
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_signature.exceptions import PipeSignatureNotExecutableError
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.pipe_signature.pipe_signature_runtime import PipeSignatureRuntime
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants
from tests.integration.pipelex.pipe_signature.conftest import SIGNATURES_DOMAIN_CODE

if TYPE_CHECKING:
    from pipelex.core.stuffs.text_content import TextContent


def _make_runtime(blueprint: PipeSignatureBlueprint, pipe_code: str = "sig_pipe") -> PipeSignatureRuntime:
    return PipeFactory[PipeSignatureRuntime].make_from_blueprint(
        domain_code=SIGNATURES_DOMAIN_CODE,
        pipe_code=pipe_code,
        blueprint=blueprint,
        concept_codes_from_the_same_domain=["SigTestDoc", "SigTestSummary"],
    )


class TestPipeSignatureRuntime:
    def test_factory_produces_runtime_from_blueprint(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="SigTestSummary")
        runtime = _make_runtime(blueprint)
        assert isinstance(runtime, PipeSignatureRuntime)
        assert runtime.type == PipeType.PIPE_SIGNATURE
        assert runtime.pipe_category == PipeCategory.PIPE_SIGNATURE

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
        dry_run_output = await dry_run_pipe(runtime, allow_signatures=True)
        assert dry_run_output.status is DryRunStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_dry_run_produces_mock_variable_list(
        self,
        setup_signature_library: Callable[[], None],
        make_signature_blueprint: Callable[..., PipeSignatureBlueprint],
    ) -> None:
        setup_signature_library()
        blueprint = make_signature_blueprint(inputs={"doc": "SigTestDoc"}, output="Text[]")
        runtime = _make_runtime(blueprint, pipe_code="sig_for_text_list")
        needed = convert_to_working_memory_format(needed_inputs_spec=runtime.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed)
        await runtime.run_pipe(
            job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED),
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
        needed = convert_to_working_memory_format(needed_inputs_spec=runtime.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed)
        await runtime.run_pipe(
            job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED),
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
            await runtime._live_run_pipe(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=SpecialPipelineId.UNTITLED),
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
