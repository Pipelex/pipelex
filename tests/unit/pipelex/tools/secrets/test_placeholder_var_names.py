import pytest
from pytest_mock import MockerFixture

from pipelex.tools.secrets.secrets_utils import placeholder_var_names


class TestPlaceholderVarNames:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("no placeholder at all", []),
            ("${API_KEY}", ["API_KEY"]),
            ("Bearer ${env:TOKEN}", ["TOKEN"]),
            ("${secret:API_KEY}", ["API_KEY"]),
            ("${env:PRIMARY|secret:FALLBACK}", ["PRIMARY", "FALLBACK"]),
            ("${env: SPACED | secret: OTHER }", ["SPACED", "OTHER"]),
            ("${A}/${B}/${A}", ["A", "B"]),
            ("${foo:BAR}", ["BAR"]),
            ('"${QUOTED}"', ["QUOTED"]),
        ],
    )
    def test_it_names_every_variable_once_in_order(self, content: str, expected: list[str]) -> None:
        assert placeholder_var_names(content=content) == expected

    def test_it_asks_no_provider_and_reads_no_environment(self, mocker: MockerFixture) -> None:
        """Naming is all it does: the keyless boot relies on that to resolve nothing."""
        get_optional_env = mocker.patch("pipelex.tools.secrets.secrets_utils.get_optional_env")
        get_required_env = mocker.patch("pipelex.tools.secrets.secrets_utils.get_required_env")

        placeholder_var_names(content="${env:A|secret:B} ${C}")

        get_optional_env.assert_not_called()
        get_required_env.assert_not_called()
