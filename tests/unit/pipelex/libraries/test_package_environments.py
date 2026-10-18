from collections.abc import Callable

import pytest
from mthds.protocol.problem.registry import ProblemDomain
from pytest_mock import MockerFixture

from pipelex.core.method_trees.requirements_file import RequirementLine, parse_requirements_text
from pipelex.errors.problem import ProblemView
from pipelex.libraries.exceptions import PipeFuncPackageSetUnstatedError
from pipelex.libraries.package_environments import InterpreterPackageEnvironment, OfferedPackageEnvironment, resolve_pipe_func_package_environment
from pipelex.plugins.pipe_func_package_offer_registry import (
    PipeFuncPackageOffer,
    PipeFuncPackageOfferFactoryFn,
    PipeFuncPackageOfferRequest,
    PipeFuncPackageRefusal,
)
from pipelex.system.configuration.pipe_func_config import PipeFuncConfig
from tests.unit.pipelex.libraries.test_data import MethodRequirementsTestData

_MODULE = "pipelex.libraries.package_environments"


def _requirements(text: str) -> list[RequirementLine]:
    return parse_requirements_text(text=text).requirements


class TestPackageEnvironments:
    def test_in_direct_mode_the_environment_is_this_interpreter_whatever_the_requirements(self, mocker: MockerFixture) -> None:
        registry = mocker.patch(f"{_MODULE}.get_pipe_func_package_offer_registry")
        mocker.patch(f"{_MODULE}.is_pipe_func_sandbox_hosted", return_value=False)

        environment = resolve_pipe_func_package_environment(requirements=_requirements("polars>=1\n"), names_host_paths=True)

        assert isinstance(environment, InterpreterPackageEnvironment)
        registry.assert_not_called()

    def test_in_a_sandbox_mode_the_factory_is_given_the_requirements_and_its_offer_is_the_environment(
        self, mocker: MockerFixture, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        factory = mocker.Mock(return_value=MethodRequirementsTestData.sandbox_offer())
        pipe_func_config = sandbox_offering(offers={"daytona": factory})
        requirements = _requirements("pandas>=2\n# spreadsheets\nopenpyxl; sys_platform == 'linux'\n")

        environment = resolve_pipe_func_package_environment(requirements=requirements, names_host_paths=True)

        assert isinstance(environment, OfferedPackageEnvironment)
        factory.assert_called_once_with(PipeFuncPackageOfferRequest(pipe_func_config=pipe_func_config, requirements=tuple(requirements)))
        (request,) = factory.call_args.args
        assert [(line.line_number, line.text) for line in request.requirements] == [(1, "pandas>=2"), (3, "openpyxl; sys_platform == 'linux'")]
        assert environment.description == MethodRequirementsTestData.SANDBOX_ENVIRONMENT
        assert environment.version_of(distribution_name="zope-interface") == "7.0"
        assert environment.version_of(distribution_name="polars") is None
        assert environment.dependencies_of(distribution_name="pandas") is None

    def test_a_refusal_the_factory_answers_is_returned_as_it_came(
        self, mocker: MockerFixture, sandbox_offering: Callable[..., PipeFuncConfig]
    ) -> None:
        refusal = PipeFuncPackageRefusal(environment="the Daytona sandbox", reason="pandas<3 conflicts with the base snapshot's pandas 3.0.1")
        sandbox_offering(offers={"daytona": mocker.Mock(return_value=refusal)})

        answer = resolve_pipe_func_package_environment(requirements=_requirements("pandas<3\n"), names_host_paths=True)

        assert answer is refusal

    @pytest.mark.parametrize(
        ("topic", "offer_registered", "remedy"),
        [
            ("no plugin registers the mode's packages", False, "must register its package offer with PluginRegistrar.add_pipe_func_package_offer"),
            ("the registered plugin cannot state them", True, "Check the plugin's configuration"),
        ],
    )
    def test_a_sandbox_mode_without_a_stated_package_set_fails_closed_naming_its_remedy(
        self, sandbox_offering: Callable[..., PipeFuncConfig], topic: str, offer_registered: bool, remedy: str
    ) -> None:
        """No requirement can be judged, so a method declaring one is refused, as the deployment's fault rather than the method's."""

        def unstated(_request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
            return None

        offers: dict[str, PipeFuncPackageOfferFactoryFn] = {"daytona": unstated} if offer_registered else {"elsewhere": unstated}
        sandbox_offering(offers=offers)

        with pytest.raises(PipeFuncPackageSetUnstatedError) as exc_info:
            resolve_pipe_func_package_environment(requirements=_requirements("pandas\n"), names_host_paths=True)

        assert exc_info.value.execution_mode == "daytona"
        assert exc_info.value.offer_registered is offer_registered, topic
        assert remedy in exc_info.value.message, topic
        assert ("registers a package offer that could not state" in exc_info.value.message) is offer_registered, topic
        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.domain == ProblemDomain.OPERATOR, topic
        assert exc_info.value.message not in str(caller.to_wire()), topic
