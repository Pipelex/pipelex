from collections.abc import Callable, Mapping
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOfferFactoryFn, PipeFuncPackageOfferRegistry
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig

_PACKAGE_ENVIRONMENTS = "pipelex.libraries.package_environments"


@pytest.fixture
def sandbox_offering(mocker: MockerFixture) -> Callable[..., PipeFuncConfig]:
    """Run PipeFunc steps in the `daytona` mode with the package-offer factories given to `sandbox_offering(offers=...)` registered.

    The call returns the mode's pipe_func config, the one each factory receives in its request.
    """

    def offering(*, offers: Mapping[str, PipeFuncPackageOfferFactoryFn]) -> PipeFuncConfig:
        pipe_func_config = PipeFuncConfig(execution_mode="daytona")
        mocker.patch(f"{_PACKAGE_ENVIRONMENTS}.is_pipe_func_sandbox_hosted", return_value=True)
        mocker.patch(f"{_PACKAGE_ENVIRONMENTS}.get_pipe_func_execution_mode", return_value="daytona")
        mocker.patch(f"{_PACKAGE_ENVIRONMENTS}.get_pipe_func_package_offer_registry", return_value=PipeFuncPackageOfferRegistry(offers))
        mocker.patch(f"{_PACKAGE_ENVIRONMENTS}.get_config", return_value=SimpleNamespace(interpreter=SimpleNamespace(pipe_func=pipe_func_config)))
        return pipe_func_config

    return offering
