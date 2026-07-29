from pathlib import Path
from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture, MockType

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


def _count_llm_report_calls(report_spy: MockType) -> int:
    return sum(1 for call in report_spy.call_args_list if isinstance(call.kwargs.get("inference_job"), LLMJob))


def _assert_hiking_trip_report_shape(content: Any) -> None:  # pyright: ignore[reportExplicitAny, reportAny]
    """Validate a runtime-generated HikingTripReport instance via attribute access.

    The HikingTripReport class is generated dynamically from the inline structure declaration
    in the .mthds fixture, so this test cannot import it as a static type. We validate by
    checking attributes against the field types declared in the fixture.
    """
    assert isinstance(getattr(content, "trail_name", None), str)  # pyright: ignore[reportAny]
    assert isinstance(getattr(content, "location", None), str)  # pyright: ignore[reportAny]
    distance_km = getattr(content, "distance_km", None)
    assert isinstance(distance_km, (int, float))
    assert isinstance(getattr(content, "elevation_gain_m", None), int)  # pyright: ignore[reportAny]
    assert isinstance(getattr(content, "difficulty", None), str)  # pyright: ignore[reportAny]
    duration_hours = getattr(content, "duration_hours", None)
    assert isinstance(duration_hours, (int, float))
    assert isinstance(getattr(content, "best_season", None), str)  # pyright: ignore[reportAny]
    assert isinstance(getattr(content, "final_verdict", None), str)  # pyright: ignore[reportAny]
    for list_field in ("gear_essentials", "trail_highlights", "warnings", "recommended_for"):
        list_value = getattr(content, list_field, None)
        assert isinstance(list_value, list)
        for item in list_value:  # pyright: ignore[reportUnknownVariableType]
            assert isinstance(item, str)


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPreliminaryTextInlineE2E:
    """End-to-end test of `structuring_method = preliminary_text` on a concept whose structure
    is declared inline in the .mthds file (no Python class).

    The MTHDS fixture (`preliminary_text_inline_e2e.mthds`) declares a `HikingTripReport`
    concept with twelve fields — including numbers, integers and several lists of text —
    directly via `[concept.HikingTripReport.structure]`. Pipelex generates the backing
    Pydantic class at library load time and registers it. The two pipes exercise the
    elaborated path on both single-output and dynamic-list-output forms.
    """

    @pytest.mark.parametrize(
        ("pipe_code", "brief", "expected_is_list"),
        [
            (
                "report_one_hike",
                "An autumn day-hike to a quiet alpine lake reachable from a trailhead near a small mountain town.",
                False,
            ),
            (
                "report_weekend_hikes",
                "A long weekend in coastal Oregon, looking for two or three trails of different difficulty levels.",
                True,
            ),
        ],
    )
    async def test_preliminary_text_with_inline_structure(
        self,
        mocker: MockerFixture,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        pipe_code: str,
        brief: str,
        expected_is_list: bool,
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])

        user_facing_pipe = get_required_pipe(pipe_code=pipe_code)
        assert isinstance(user_facing_pipe, PipeSequence)
        assert len(user_facing_pipe.sequential_sub_pipes) == 2
        assert user_facing_pipe.sequential_sub_pipes[0].pipe_code == f"{pipe_code}__draft_text"
        assert user_facing_pipe.sequential_sub_pipes[1].pipe_code == f"{pipe_code}__structure"

        structure_step = get_required_pipe(pipe_code=f"{pipe_code}__structure")
        assert isinstance(structure_step, PipeStructure)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text=brief),
                name="hike_brief",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=user_facing_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        report_spy = mocker.spy(get_report_delegate(), "report_inference_job")
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)
        pretty_print(pipe_output, title=f"preliminary_text inline-structure output ({pipe_code})")

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("draft_text") is not None
        if pipe_run_mode.is_live:
            # Exactly two LLM calls: one for the draft text, one for the structuring step.
            assert _count_llm_report_calls(report_spy) == 2
            assert pipe_output.main_stuff.concept.code == "HikingTripReport"
            if expected_is_list:
                items = pipe_output.main_stuff_as_items(item_type=StructuredContent)
                assert len(items) >= 1
                for item in items:
                    _assert_hiking_trip_report_shape(item)
            else:
                _assert_hiking_trip_report_shape(pipe_output.main_stuff.content)
