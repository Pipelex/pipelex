import shlex
import sys
from importlib.metadata import PackageNotFoundError

import pytest
from packaging.markers import Marker
from packaging.version import InvalidVersion
from pytest_mock import MockerFixture

from pipelex.libraries.method_requirements import marker_variables_of, parse_requirements_text, unmet_requirements
from pipelex.libraries.package_environments import InterpreterPackageEnvironment, OfferedPackageEnvironment
from tests.unit.pipelex.libraries.test_data import MethodRequirementsTestData

_DISTRIBUTION_TARGET = "pipelex.libraries.package_environments.distribution"


def _unmet_reasons(*, text: str, environment: InterpreterPackageEnvironment | OfferedPackageEnvironment) -> list[str]:
    parsed = parse_requirements_text(text=text)
    assert parsed.refused_lines == []
    return [unmet_requirement.reason for unmet_requirement in unmet_requirements(requirements=parsed.requirements, environment=environment)]


def _install(mocker: MockerFixture, *, installed: dict[str, tuple[str, list[str]]]) -> None:
    """Make this interpreter appear to hold exactly `installed`: each name with its version and its Requires-Dist."""

    def fake_distribution(distribution_name: str) -> object:
        normalized = distribution_name.lower().replace("_", "-")
        if normalized not in installed:
            raise PackageNotFoundError(distribution_name)
        version, requires = installed[normalized]
        return mocker.Mock(version=version, requires=requires)

    mocker.patch(_DISTRIBUTION_TARGET, side_effect=fake_distribution)


class TestMethodRequirementsJudgment:
    @pytest.mark.parametrize(
        ("topic", "line", "expected_reason"),
        [
            ("range met", "pandas>=2.2,<3", None),
            ("pin met", "openpyxl==3.1.5", None),
            ("names compared normalized", "zope-interface>=7\nOpenPyXL==3.1.5", None),
            ("a pre-release held counts", "numpy>=2", None),
            ("version not accepted", "pandas>=3", "pandas 2.2.3 is there"),
            ("package not offered", "polars>=1", "polars is missing"),
            ("marker false means not needed", 'pywin32; sys_platform == "win32"', None),
            ("marker true is judged", 'polars; sys_platform == "linux"', "polars is missing"),
            ("a line names no extra", 'polars; extra == "fast"', None),
            ("marker variable not stated", 'pandas; platform_release >= "6"', "its marker reads platform_release, which the Daytona sandbox"),
            ("extras are not stated", "pandas[excel]>=2", "does not state what the extra 'excel' of pandas needs"),
        ],
    )
    def test_a_stated_package_set_judges_each_requirement(self, topic: str, line: str, expected_reason: str | None) -> None:
        """The offer is the whole environment: its distributions, its marker values, and nothing it does not state."""
        environment = OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer())

        reasons = _unmet_reasons(text=line, environment=environment)

        if expected_reason is None:
            assert reasons == [], topic
        else:
            (reason,) = reasons
            assert expected_reason in reason, topic

    def test_a_marker_value_spelled_like_a_variable_is_not_read_as_one(self) -> None:
        """Only the marker's variables are checked against what an environment states, never its quoted values."""
        parsed = parse_requirements_text(text='pandas; os_name == "python_full_version"\n')

        (requirement_line,) = parsed.requirements
        assert requirement_line.requirement.marker is not None
        assert marker_variables_of(marker=requirement_line.requirement.marker) == {"os_name"}
        environment = OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer())
        assert unmet_requirements(requirements=parsed.requirements, environment=environment) == []

    def test_this_interpreter_meets_what_it_holds(self) -> None:
        """Read for real: pipelex's own dependencies are installed here, and a package no index holds is not."""
        reasons = _unmet_reasons(
            text="pydantic>=2\nPyYAML\npipelex-requirements-test-absent>=1\n", environment=InterpreterPackageEnvironment(names_host_paths=True)
        )

        assert reasons == ["pipelex-requirements-test-absent is missing"]

    def test_an_extra_is_followed_through_the_metadata_of_this_interpreter(self, mocker: MockerFixture) -> None:
        """An extra needs what the distribution's metadata declares under it, and only that; extras naming each other end."""
        _install(
            mocker,
            installed={
                "fastlib": ("1.4", ["basedep>=1", 'turbo>=2; extra == "speed"', 'unrelated; extra == "other"', 'fastlib[cycle]; extra == "speed"']),
                "turbo": ("1.5", []),
                "basedep": ("0.1", []),
            },
        )

        reasons = _unmet_reasons(text="fastlib[speed]>=1\nfastlib[other]\n", environment=InterpreterPackageEnvironment(names_host_paths=True))

        assert reasons == [
            "the extra 'speed' of fastlib needs 'turbo>=2; extra == \"speed\"', and turbo 1.5 is there",
            "the extra 'other' of fastlib needs 'unrelated; extra == \"other\"', and unrelated is missing",
        ]

    def test_extras_naming_each_other_are_followed_once(self, mocker: MockerFixture) -> None:
        _install(mocker, installed={"loopy": ("2.0", ['loopy[beta]; extra == "alpha"', 'loopy[alpha]; extra == "beta"'])})

        assert _unmet_reasons(text="loopy[alpha]\n", environment=InterpreterPackageEnvironment(names_host_paths=True)) == []

    def test_an_installed_version_no_specifier_compares_is_not_met(self, mocker: MockerFixture) -> None:
        _install(mocker, installed={"oddball": ("not-a-version", [])})

        (reason,) = _unmet_reasons(text="oddball>=1\n", environment=InterpreterPackageEnvironment(names_host_paths=True))

        assert reason == "oddball not-a-version is there, a version no specifier can be compared with"

    def test_each_environment_advises_its_own_remedy(self) -> None:
        """Locally the advice is the uv command for this interpreter; on a sandbox-hosted deployment it is the offer's limits."""
        local_advice = InterpreterPackageEnvironment(names_host_paths=True).advice(
            requirement_texts=["pandas>=2.2", 'tzdata; python_version >= "3.12"']
        )
        sandbox_advice = OfferedPackageEnvironment(offer=MethodRequirementsTestData.sandbox_offer()).advice(requirement_texts=["pandas>=3"])

        assert f"uv pip install --python {shlex.quote(sys.executable)} 'pandas>=2.2' 'tzdata; python_version >= \"3.12\"'" in local_advice
        assert "never installs" in local_advice
        assert MethodRequirementsTestData.SANDBOX_ENVIRONMENT in sandbox_advice
        assert "uv" not in sandbox_advice

    def test_this_interpreter_is_named_by_its_path_only_where_host_paths_may_be_named(self) -> None:
        environment = InterpreterPackageEnvironment(names_host_paths=False)

        advice = environment.advice(requirement_texts=["pandas>=2.2"])

        assert sys.executable not in environment.description
        assert sys.executable not in advice
        assert environment.description == "the Python interpreter Pipelex runs in"
        assert "uv pip install 'pandas>=2.2'" in advice

    def test_a_marker_comparing_a_value_that_is_not_a_version_refuses_the_requirement(self, mocker: MockerFixture) -> None:
        """Releases of packaging before 22 raise InvalidVersion where later ones compare as strings; the requirement is refused, not the load."""
        mocker.patch.object(Marker, "evaluate", side_effect=InvalidVersion("Invalid version: '5.15.0-generic'"))

        (reason,) = _unmet_reasons(text='pandas; platform_release >= "5"\n', environment=InterpreterPackageEnvironment(names_host_paths=True))

        assert reason == "its marker cannot be evaluated: Invalid version: '5.15.0-generic'"
