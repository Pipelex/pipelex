from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.exceptions import ConceptError
from pipelex.core.pipes.output.output_renderer import _collect_possible_outputs  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]

GET_REQUIRED_PIPE_TARGET = "pipelex.core.pipes.output.output_renderer.get_required_pipe"


def _make_condition_pipe(mocker: MockerFixture, dependencies: set[str]) -> Any:
    condition_pipe = mocker.MagicMock()
    condition_pipe.type = "PipeCondition"
    condition_pipe.is_signature = False
    condition_pipe.pipe_dependencies.return_value = dependencies
    return condition_pipe


def _make_mapped_pipe(mocker: MockerFixture, concept_ref: str) -> Any:
    mapped_pipe = mocker.MagicMock()
    mapped_pipe.is_signature = False
    mapped_pipe.output.concept.concept_ref = concept_ref
    return mapped_pipe


class TestCollectPossibleOutputsCondition:
    def test_empty_dependencies_yield_no_outputs(self, mocker: MockerFixture) -> None:
        """A PipeCondition with no mapped pipes yields no possible outputs and never resolves pipes."""
        condition_pipe = _make_condition_pipe(mocker, set())
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET)

        result = _collect_possible_outputs(condition_pipe)

        assert result == []
        get_pipe_mock.assert_not_called()

    def test_single_mapped_pipe_uses_content_key(self, mocker: MockerFixture) -> None:
        """A single mapped pipe yields one entry whose content comes from the rendered dict's 'content' key."""
        condition_pipe = _make_condition_pipe(mocker, {"make_summary"})
        mapped_pipe = _make_mapped_pipe(mocker, "test.Summary")
        mapped_pipe.output.render_stuff_spec.return_value = {
            "concept": "test.Summary",
            "content": {"text": "summary text"},
        }
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = _collect_possible_outputs(condition_pipe, output_format=ConceptRepresentationFormat.JSON)

        assert result == [{"concept_ref": "test.Summary", "content": {"text": "summary text"}}]
        get_pipe_mock.assert_called_once_with(pipe_code="make_summary")
        mapped_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.JSON)

    def test_multiple_mapped_pipes_are_ordered_deterministically(self, mocker: MockerFixture) -> None:
        """With several mapped pipes, outputs come back sorted by pipe code regardless of set iteration order."""
        condition_pipe = _make_condition_pipe(mocker, {"zeta_branch", "alpha_branch", "mid_branch"})
        mapped_pipes: dict[str, Any] = {}
        for pipe_code in ("alpha_branch", "mid_branch", "zeta_branch"):
            mapped_pipe = _make_mapped_pipe(mocker, f"test.{pipe_code.title().replace('_', '')}")
            mapped_pipe.output.render_stuff_spec.return_value = {"content": {"from": pipe_code}}
            mapped_pipes[pipe_code] = mapped_pipe

        def resolve_pipe(pipe_code: str) -> Any:
            return mapped_pipes[pipe_code]

        mocker.patch(GET_REQUIRED_PIPE_TARGET, side_effect=resolve_pipe)

        result = _collect_possible_outputs(condition_pipe, output_format=ConceptRepresentationFormat.JSON)

        assert [entry["content"]["from"] for entry in result] == ["alpha_branch", "mid_branch", "zeta_branch"]

    def test_single_mapped_pipe_falls_back_to_whole_dict(self, mocker: MockerFixture) -> None:
        """When the rendered dict has no 'content' key, the whole dict is used as the content."""
        condition_pipe = _make_condition_pipe(mocker, {"build_schema"})
        rendered_dict = {"type": "object", "properties": {"name": {"type": "string"}}}
        mapped_pipe = _make_mapped_pipe(mocker, "test.Schema")
        mapped_pipe.output.render_stuff_spec.return_value = rendered_dict
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = _collect_possible_outputs(condition_pipe, output_format=ConceptRepresentationFormat.SCHEMA)

        assert result == [{"concept_ref": "test.Schema", "content": rendered_dict}]

    @pytest.mark.parametrize(
        "render_error",
        [
            ValueError("unsupported shape"),
            ConceptError("unresolved structure class"),
        ],
        ids=["value_error", "pipelex_error"],
    )
    def test_render_failure_yields_placeholder(self, mocker: MockerFixture, render_error: Exception) -> None:
        """A mapped pipe whose output cannot be rendered yields a placeholder entry instead of propagating."""
        condition_pipe = _make_condition_pipe(mocker, {"dynamic_pipe"})
        mapped_pipe = _make_mapped_pipe(mocker, "test.Dynamic")
        mapped_pipe.output.render_stuff_spec.side_effect = render_error
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = _collect_possible_outputs(condition_pipe)

        assert result == [{"concept_ref": "test.Dynamic", "content": "<unable to render>"}]

    @pytest.mark.parametrize("pipe_type", ["PipeLLM", "PipeImgGen"])
    def test_operator_pipe_types_yield_no_outputs(self, mocker: MockerFixture, pipe_type: str) -> None:
        """Operator pipe types have no mapped outputs to collect."""
        operator_pipe = mocker.MagicMock()
        operator_pipe.type = pipe_type
        operator_pipe.is_signature = False
        get_pipe_mock = mocker.patch(GET_REQUIRED_PIPE_TARGET)

        result = _collect_possible_outputs(operator_pipe)

        assert result == []
        get_pipe_mock.assert_not_called()
