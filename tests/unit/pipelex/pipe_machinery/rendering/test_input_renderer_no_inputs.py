"""Unit tests for the inputs renderer's answer to a pipe that declares no inputs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_machinery.rendering.input_renderer import build_inputs_template, render_inputs

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


def _pipe_without_inputs() -> PipeAbstract:
    # The empty-inputs check runs before any concept is resolved, so a stub stands in for the pipe;
    # its bare code differs from its ref so the message proves which one it names.
    return cast("PipeAbstract", SimpleNamespace(code="greet", pipe_ref="inputs_probe.greet", inputs=SimpleNamespace(root={})))


class TestInputRendererNoInputs:
    def test_template_names_the_qualified_pipe_ref(self) -> None:
        """The template builder refuses a pipe without inputs with a message naming its qualified ref."""
        with pytest.raises(NoInputsRequiredError) as exc_info:
            build_inputs_template(_pipe_without_inputs())

        assert str(exc_info.value) == "Pipe 'inputs_probe.greet' declares no inputs."

    def test_render_inputs_propagates_the_same_message(self) -> None:
        """The JSON renderer, which the inputs commands call, raises the same message."""
        with pytest.raises(NoInputsRequiredError, match=r"^Pipe 'inputs_probe\.greet' declares no inputs\.$"):
            render_inputs(_pipe_without_inputs())
