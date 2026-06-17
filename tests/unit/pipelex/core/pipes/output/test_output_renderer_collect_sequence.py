from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.exceptions import ConceptError
from pipelex.core.pipes.output.output_renderer import _collect_possible_outputs  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]

GET_REQUIRED_PIPE_TARGET = "pipelex.core.pipes.output.output_renderer.get_required_pipe"


def _make_sequence_pipe(mocker: MockerFixture, sub_pipe_codes: list[str]) -> Any:
    sequence_pipe = mocker.MagicMock()
    sequence_pipe.type = "PipeSequence"
    sequence_pipe.is_signature = False
    sub_pipes: list[Any] = []
    for sub_pipe_code in sub_pipe_codes:
        sub_pipe = mocker.MagicMock()
        sub_pipe.pipe_code = sub_pipe_code
        sub_pipes.append(sub_pipe)
    sequence_pipe.sequential_sub_pipes = sub_pipes
    return sequence_pipe


def _make_concrete_pipe(mocker: MockerFixture, concept_ref: str) -> Any:
    concrete_pipe = mocker.MagicMock()
    concrete_pipe.type = "PipeLLM"
    concrete_pipe.is_signature = False
    concrete_pipe.output.concept.code = "Text"
    concrete_pipe.output.concept.concept_ref = concept_ref
    return concrete_pipe


class TestCollectPossibleOutputsSequence:
    def test_empty_sub_pipes_yield_no_outputs(self, mocker: MockerFixture) -> None:
        """A PipeSequence with no sub-pipes yields no possible outputs and never resolves pipes."""
        sequence_pipe = _make_sequence_pipe(mocker, [])
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET)

        result = _collect_possible_outputs(sequence_pipe)

        assert result == []
        get_pipe_mock.assert_not_called()

    def test_last_sub_pipe_with_empty_code_yields_no_outputs(self, mocker: MockerFixture) -> None:
        """A last sub-pipe with an empty pipe_code yields no possible outputs."""
        sequence_pipe = _make_sequence_pipe(mocker, ["first_step", ""])
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET)

        result = _collect_possible_outputs(sequence_pipe)

        assert result == []
        get_pipe_mock.assert_not_called()

    def test_concrete_last_pipe_yields_single_entry(self, mocker: MockerFixture) -> None:
        """Only the last sub-pipe is resolved and its rendered output is the single possible output."""
        sequence_pipe = _make_sequence_pipe(mocker, ["first_step", "final_step"])
        final_pipe = _make_concrete_pipe(mocker, "test.Final")
        final_pipe.output.render_stuff_spec.return_value = {
            "concept": "test.Final",
            "content": {"text": "final output"},
        }
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=final_pipe)

        result = _collect_possible_outputs(sequence_pipe, output_format=ConceptRepresentationFormat.JSON)

        assert result == [{"concept_ref": "test.Final", "content": {"text": "final output"}}]
        get_pipe_mock.assert_called_once_with(pipe_code="final_step")
        final_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.JSON)

    @pytest.mark.parametrize(
        "render_error",
        [
            ValueError("unsupported shape"),
            ConceptError("unresolved structure class"),
        ],
        ids=["value_error", "pipelex_error"],
    )
    def test_last_pipe_render_failure_yields_no_outputs(self, mocker: MockerFixture, render_error: Exception) -> None:
        """A last pipe whose output cannot be rendered yields no possible outputs instead of propagating."""
        sequence_pipe = _make_sequence_pipe(mocker, ["final_step"])
        final_pipe = _make_concrete_pipe(mocker, "test.Dynamic")
        final_pipe.output.render_stuff_spec.side_effect = render_error
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=final_pipe)

        result = _collect_possible_outputs(sequence_pipe)

        assert result == []

    def test_anything_last_pipe_recurses_into_it(self, mocker: MockerFixture) -> None:
        """When the last pipe itself outputs Anything, collection recurses into it down to the concrete leaf."""
        outer_pipe = _make_sequence_pipe(mocker, ["step_one", "mid_sequence"])
        mid_pipe = _make_sequence_pipe(mocker, ["leaf_step"])
        mid_pipe.output.concept.code = "Anything"
        leaf_pipe = _make_concrete_pipe(mocker, "test.Leaf")
        leaf_pipe.output.render_stuff_spec.return_value = {
            "concept": "test.Leaf",
            "content": {"text": "leaf output"},
        }
        pipes_by_code = {"mid_sequence": mid_pipe, "leaf_step": leaf_pipe}

        def fake_get_required_pipe(pipe_code: str) -> Any:
            return pipes_by_code[pipe_code]

        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET, side_effect=fake_get_required_pipe)

        result = _collect_possible_outputs(outer_pipe, output_format=ConceptRepresentationFormat.JSON)

        assert result == [{"concept_ref": "test.Leaf", "content": {"text": "leaf output"}}]
        assert get_pipe_mock.call_count == 2
        get_pipe_mock.assert_any_call(pipe_code="mid_sequence")
        get_pipe_mock.assert_any_call(pipe_code="leaf_step")
        leaf_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.JSON)
