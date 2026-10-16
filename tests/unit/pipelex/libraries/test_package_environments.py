from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ErrorDomain
from pipelex.libraries.exceptions import PipeFuncPackageSetUnstatedError
from pipelex.libraries.package_environments import InterpreterPackageEnvironment, OfferedPackageEnvironment, resolve_pipe_func_package_environment
from pipelex.plugins.pipe_func_package_offer_registry import PipeFuncPackageOffer, PipeFuncPackageOfferFactoryFn, PipeFuncPackageOfferRegistry
from tests.unit.pipelex.libraries.test_data import MethodRequirementsTestData

_MODULE = "pipelex.libraries.package_environments"


def _sandbox_hosted(mocker: MockerFixture, *, offers: dict[str, PipeFuncPackageOfferFactoryFn]) -> object:
    """Make this process run PipeFunc steps in the `daytona` mode, with the given offers registered; return its pipe_func config."""
    pipe_func_config = object()
    mocker.patch(f"{_MODULE}.is_pipe_func_sandbox_hosted", return_value=True)
    mocker.patch(f"{_MODULE}.get_pipe_func_execution_mode", return_value="daytona")
    mocker.patch(f"{_MODULE}.get_pipe_func_package_offer_registry", return_value=PipeFuncPackageOfferRegistry(offers))
    mocker.patch(f"{_MODULE}.get_config", return_value=SimpleNamespace(interpreter=SimpleNamespace(pipe_func=pipe_func_config)))
    return pipe_func_config


class TestPackageEnvironments:
    def test_in_direct_mode_the_environment_is_this_interpreter(self, mocker: MockerFixture) -> None:
        registry = mocker.patch(f"{_MODULE}.get_pipe_func_package_offer_registry")
        mocker.patch(f"{_MODULE}.is_pipe_func_sandbox_hosted", return_value=False)

        environment = resolve_pipe_func_package_environment()

        assert isinstance(environment, InterpreterPackageEnvironment)
        registry.assert_not_called()

    def test_in_a_sandbox_mode_the_environment_is_the_offer_its_plugin_states(self, mocker: MockerFixture) -> None:
        factory = mocker.Mock(return_value=MethodRequirementsTestData.sandbox_offer())
        pipe_func_config = _sandbox_hosted(mocker, offers={"daytona": factory})

        environment = resolve_pipe_func_package_environment()

        assert isinstance(environment, OfferedPackageEnvironment)
        factory.assert_called_once_with(pipe_func_config)
        assert environment.description == MethodRequirementsTestData.SANDBOX_ENVIRONMENT
        assert environment.version_of(distribution_name="zope-interface") == "7.0"
        assert environment.version_of(distribution_name="polars") is None
        assert environment.dependencies_of(distribution_name="pandas") is None

    @pytest.mark.parametrize("topic", ["no plugin states the mode's packages", "the plugin cannot state them"])
    def test_a_sandbox_mode_without_a_stated_package_set_fails_closed(self, mocker: MockerFixture, topic: str) -> None:
        """No requirement can be judged, so a method declaring one is refused, as the deployment's fault rather than the method's."""

        def unstated(_config: object) -> PipeFuncPackageOffer | None:
            return None

        offers: dict[str, PipeFuncPackageOfferFactoryFn] = {"elsewhere": unstated} if topic.startswith("no plugin") else {"daytona": unstated}
        _sandbox_hosted(mocker, offers=offers)

        with pytest.raises(PipeFuncPackageSetUnstatedError) as exc_info:
            resolve_pipe_func_package_environment()

        assert exc_info.value.execution_mode == "daytona"
        assert "add_pipe_func_package_offer" in exc_info.value.message
        assert exc_info.value.to_error_report().error_domain == ErrorDomain.CONFIG
