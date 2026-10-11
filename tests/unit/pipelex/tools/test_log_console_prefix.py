"""Which package name the console prints before a line's message, under each value of the ``package_prefix`` setting.

``libraries`` names another library's package and leaves a Pipelex line bare, ``all`` names every named logger's
package, Pipelex's own included, and ``none`` names nothing. A line on the root logger names no package under any value.
"""

from __future__ import annotations

import pytest

from pipelex.tools.log.console_prefix import prefixed_package_name
from pipelex.tools.log.log_config import PackagePrefix
from tests.helpers.console_log_rendering import package_log_config

LOGGER_NAMES = [
    "pipelex.cogt.inference",
    "pipelex_api.security",
    "pipelex_temporal.worker",
    "manifold_client.manifold_native_client",
    "httpx._client",
    "root",
]
LOGGER_IDS = ["the runtime", "the API server", "a pipelex_ plugin", "a plugin named otherwise", "another library", "the root logger"]


class TestPrefixedPackageName:
    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        list(zip(LOGGER_NAMES, [None, None, None, "manifold_client", "httpx", None], strict=True)),
        ids=LOGGER_IDS,
    )
    def test_libraries_names_the_package_of_a_logger_outside_pipelex_only(self, logger_name: str, expected: str | None) -> None:
        assert prefixed_package_name(logger_name=logger_name, package_prefix=PackagePrefix.LIBRARIES) == expected

    @pytest.mark.parametrize(
        ("logger_name", "expected"),
        list(zip(LOGGER_NAMES, ["pipelex", "pipelex_api", "pipelex_temporal", "manifold_client", "httpx", None], strict=True)),
        ids=LOGGER_IDS,
    )
    def test_all_names_the_package_of_every_named_logger(self, logger_name: str, expected: str | None) -> None:
        assert prefixed_package_name(logger_name=logger_name, package_prefix=PackagePrefix.ALL) == expected

    @pytest.mark.parametrize("logger_name", LOGGER_NAMES, ids=LOGGER_IDS)
    def test_none_names_no_package(self, logger_name: str) -> None:
        assert prefixed_package_name(logger_name=logger_name, package_prefix=PackagePrefix.NONE) is None

    def test_the_shipped_default_is_libraries(self) -> None:
        assert package_log_config().rich_log.package_prefix == PackagePrefix.LIBRARIES
