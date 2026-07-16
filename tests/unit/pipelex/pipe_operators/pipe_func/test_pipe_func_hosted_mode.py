from typing import Callable

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint

_UNREGISTERED = PipeFuncBlueprint(
    description="Hosted-mode case: function lives only in the sandbox, never in this process.",
    inputs={},
    output="native.Text",
    function_name="a_function_that_is_not_registered_here",
)


def _make_pipe_func() -> PipeFunc:
    return PipeFactory[PipeFunc].make_from_blueprint(
        domain_code="hosted_test",
        pipe_code="hosted_pipe",
        blueprint=_UNREGISTERED,
    )


class TestPipeFuncHostedMode:
    """In sandbox-hosted mode the PipeFunc validators accept a function that is absent from this
    process's func_registry; in local/direct mode the same input still raises.
    """

    def test_local_mode_rejects_unregistered_function(self, load_empty_library: Callable[[], str]):
        """Default (local) mode is unchanged: an unregistered function_name fails construction."""
        load_empty_library()
        with pytest.raises(ValidationError, match="not found in registry"):
            _make_pipe_func()

    def test_hosted_mode_accepts_unregistered_function_name(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """Hosted mode skips the func_registry lookup, so the declared name is accepted verbatim."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        pipe_func = _make_pipe_func()

        assert pipe_func.function_name == "a_function_that_is_not_registered_here"

    def test_hosted_mode_skips_output_validation(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ):
        """validate_output_with_library is a no-op in hosted mode (the sandbox validates for real)."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        pipe_func = _make_pipe_func()
        # Must not raise even though the function is not registered and its return type is unknown here.
        pipe_func.validate_output_with_library()
