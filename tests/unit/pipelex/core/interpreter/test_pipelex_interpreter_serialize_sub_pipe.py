from typing import Any

import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipelexInterpreterSerializeSubPipe:
    @pytest.mark.parametrize(
        "sub_pipe_blueprint,expected_result",
        [
            # Basic sub pipe (step in sequence)
            (
                SubPipeBlueprint(
                    pipe="step1",
                    result="intermediate1",
                ),
                {
                    "pipe": "step1",
                    "result": "intermediate1",
                },
            ),
            # Sub pipe with nb_output
            (
                SubPipeBlueprint(
                    pipe="generate_ideas",
                    result="ideas",
                    nb_output=3,
                ),
                {
                    "pipe": "generate_ideas",
                    "result": "ideas",
                    "nb_output": 3,
                },
            ),
            # Sub pipe with multiple_output
            (
                SubPipeBlueprint(
                    pipe="brainstorm",
                    result="solutions",
                    multiple_output=True,
                ),
                {
                    "pipe": "brainstorm",
                    "result": "solutions",
                    "multiple_output": True,
                },
            ),
            # Sub pipe with batch_over and batch_as
            (
                SubPipeBlueprint(
                    pipe="process_items",
                    result="processed_items",
                    batch_over="input_list",
                    batch_as="current_item",
                ),
                {
                    "pipe": "process_items",
                    "result": "processed_items",
                    "batch_over": "input_list",
                    "batch_as": "current_item",
                },
            ),
            # Sub pipe with nb_output and batch fields (no multiple_output)
            (
                SubPipeBlueprint(
                    pipe="complex_step",
                    result="complex_result",
                    nb_output=2,
                    batch_over="items",
                    batch_as="item",
                ),
                {
                    "pipe": "complex_step",
                    "result": "complex_result",
                    "nb_output": 2,
                    "batch_over": "items",
                    "batch_as": "item",
                },
            ),
            # Sub pipe with batch_over=False (default, should not be included)
            (
                SubPipeBlueprint(
                    pipe="simple_step",
                    result="simple_result",
                    batch_over=False,  # This is the default and should not appear in output
                ),
                {
                    "pipe": "simple_step",
                    "result": "simple_result",
                    # batch_over=False should not be included since it's the default
                },
            ),
        ],
    )
    def test_serialize_sub_pipe(self, sub_pipe_blueprint: SubPipeBlueprint, expected_result: dict[str, Any]):
        result = PipelexInterpreter.serialize_sub_pipe(sub_pipe_blueprint)
        assert result == expected_result

    @pytest.mark.parametrize(
        "sub_pipe_blueprint,expected_plx_string",
        [
            # Basic sub pipe (step in sequence)
            (
                SubPipeBlueprint(
                    pipe="step1",
                    result="intermediate1",
                ),
                '{ pipe = "step1", result = "intermediate1" }',
            ),
            # Sub pipe with nb_output
            (
                SubPipeBlueprint(
                    pipe="generate_ideas",
                    result="ideas",
                    nb_output=3,
                ),
                '{ pipe = "generate_ideas", result = "ideas", nb_output = 3 }',
            ),
            # Sub pipe with multiple_output
            (
                SubPipeBlueprint(
                    pipe="brainstorm",
                    result="solutions",
                    multiple_output=True,
                ),
                '{ pipe = "brainstorm", result = "solutions", multiple_output = true }',
            ),
            # Sub pipe with batch_over and batch_as
            (
                SubPipeBlueprint(
                    pipe="process_items",
                    result="processed_items",
                    batch_over="input_list",
                    batch_as="current_item",
                ),
                '{ pipe = "process_items", result = "processed_items", batch_over = "input_list", batch_as = "current_item" }',
            ),
            # Sub pipe with batch_over=False (default, should not be included)
            (
                SubPipeBlueprint(
                    pipe="simple_step",
                    result="simple_result",
                    batch_over=False,  # This is the default and should not appear in output
                ),
                '{ pipe = "simple_step", result = "simple_result" }',
            ),
        ],
    )
    def test_sub_pipe_to_plx_string(self, sub_pipe_blueprint: SubPipeBlueprint, expected_plx_string: str):
        result = PipelexInterpreter.sub_pipe_to_plx_string(sub_pipe_blueprint)
        assert result == expected_plx_string
