from collections.abc import Callable
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_pipe_library, get_required_pipe
from pipelex.libraries.pipe.pipe_library import PipeLibrary
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.execution_chain import make_direct_chain
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.unit.pipelex.graph.conftest import make_trace_context

_DEPENDENCY_ALIAS = "risk_pack"


def _make_outcome_pipe(*, domain_code: str, pipe_code: str) -> PipeCompose:
    return PipeFactory[PipeCompose].make_from_blueprint(
        domain_code=domain_code,
        pipe_code=pipe_code,
        blueprint=PipeComposeBlueprint(description=f"The {pipe_code} outcome", inputs={}, output="native.Text", template=pipe_code),
    )


def _load_outcome_pipes() -> None:
    """The filings domain's own outcome pipes, and a dependency package's `risk.deep_checks`."""
    pipe_library = get_pipe_library()
    # The library a test opens is the concrete one, which holds a dependency package's pipes under their alias.
    assert isinstance(pipe_library, PipeLibrary)
    for pipe_code in ("deep_checks", "quick_check", "legal_check", "file_away"):
        pipe_library.add_new_pipe(pipe=_make_outcome_pipe(domain_code="filings", pipe_code=pipe_code))
    pipe_library.add_dependency_pipe(alias=_DEPENDENCY_ALIAS, pipe=_make_outcome_pipe(domain_code="risk", pipe_code="deep_checks"), is_exported=True)


def _make_condition(*, outcomes: dict[str, str | SpecialOutcome], default_outcome: str | SpecialOutcome) -> PipeCondition:
    return PipeFactory[PipeCondition].make_from_blueprint(
        domain_code="filings",
        pipe_code="choose_depth",
        blueprint=PipeConditionBlueprint(
            description="Check the filings in depth, quickly, or not at all",
            inputs={"depth": "native.Text"},
            output="native.Text?",
            expression="depth",
            outcomes=outcomes,
            default_outcome=default_outcome,
        ),
    )


def _make_filings_condition(*, default_outcome: str | SpecialOutcome) -> PipeCondition:
    return _make_condition(
        outcomes={
            "detailed": "filings.deep_checks",
            "quick": "filings.quick_check",
            "high risk": "filings.deep_checks",
            "legal/tax review": "filings.legal_check",
            "skip": SpecialOutcome.CONTINUE,
        },
        default_outcome=default_outcome,
    )


def _make_condition_spelling_one_pipe_two_ways() -> PipeCondition:
    """The dependency's `risk.deep_checks`, written with its domain by a key and without it by the default outcome."""
    return _make_condition(
        outcomes={"quick": "filings.quick_check", "detailed": f"{_DEPENDENCY_ALIAS}->risk.deep_checks"},
        default_outcome=f"{_DEPENDENCY_ALIAS}->deep_checks",
    )


class TestPipeConditionOutcomeGroups:
    @pytest.mark.parametrize(
        ("default_outcome", "pipe_ref", "expected_segment"),
        [
            ("filings.file_away", "filings.deep_checks", "outcome_detailed"),
            ("filings.file_away", "filings.quick_check", "outcome_quick"),
            ("filings.file_away", "filings.legal_check", "outcome_legal%2Ftax%20review"),
            ("filings.file_away", "filings.file_away", "default"),
            ("filings.quick_check", "filings.quick_check", "outcome_quick"),
        ],
        ids=["group_of_two_keys", "group_of_one_key", "encoded_key", "group_only_the_default_runs", "default_joins_a_key_group"],
    )
    def test_each_pipe_runs_at_the_segment_of_its_outcome_group(
        self, load_empty_library: Callable[[], str], default_outcome: str, pipe_ref: str, expected_segment: str
    ) -> None:
        load_empty_library()
        _load_outcome_pipes()
        condition = _make_filings_condition(default_outcome=default_outcome)

        assert condition.outcome_group_segment(pipe=get_required_pipe(pipe_code=pipe_ref)) == expected_segment

    def test_outcomes_spelling_one_pipe_differently_form_one_group(self, load_empty_library: Callable[[], str]) -> None:
        """Outcomes are grouped by the pipe the library resolves them to, not by how they spell it."""
        load_empty_library()
        _load_outcome_pipes()
        condition = _make_condition_spelling_one_pipe_two_ways()
        dependency_pipe = get_required_pipe(pipe_code=f"{_DEPENDENCY_ALIAS}->risk.deep_checks")
        assert get_required_pipe(pipe_code=f"{_DEPENDENCY_ALIAS}->deep_checks") is dependency_pipe

        assert condition.outcome_group_segment(pipe=dependency_pipe) == "outcome_detailed"
        # The host's own `filings.deep_checks` shares the dependency's code and is another pipe, in no group here.
        assert condition.outcome_group_segment(pipe=get_required_pipe(pipe_code="filings.deep_checks")) == "default"
        assert [pipe.pipe_ref for pipe in condition.outcome_group_pipes()] == ["filings.quick_check", "risk.deep_checks"]
        assert condition.outcome_group_pipes()[-1] is dependency_pipe

    @pytest.mark.asyncio(loop_scope="function")
    async def test_a_dry_run_runs_each_group_once_at_its_path(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """A dry run runs the pipe of every group, once however many outcomes spell it, at the segment a live run gives it."""
        load_empty_library()
        _load_outcome_pipes()
        condition = _make_condition_spelling_one_pipe_two_ways()
        runs: list[tuple[str, str | None]] = []

        def _record_run(
            self: PipeCompose,
            *,
            job_metadata: JobMetadata,
            working_memory: WorkingMemory,
            **_kwargs: Any,
        ) -> PipeOutput:
            assert job_metadata.trace_context is not None
            runs.append((self.pipe_ref, job_metadata.trace_context.child_segment))
            return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

        mocker.patch.object(PipeCompose, "run_pipe", autospec=True, side_effect=_record_run)
        trace_context = make_trace_context(graph_id="run_1").model_copy(update={"parent_path": "filings.choose_depth", "chain": make_direct_chain()})
        job_metadata = JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="pytest", pipeline_run_id="run_1"),
            trace_context=trace_context,
        )

        await condition._dry_run_controller_pipe(  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )

        assert runs == [("filings.quick_check", "outcome_quick"), ("risk.deep_checks", "outcome_detailed")]
