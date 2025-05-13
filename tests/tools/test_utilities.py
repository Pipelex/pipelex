# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import inspect

import pytest

from pipelex import pretty_print
from pipelex.tools.config.manager import config_manager
from pipelex.tools.misc.utilities import cleanup_name_to_pascal_case, get_package_name


class TestUtilities:
    def test_get_package_name_here_1(self):
        frame = inspect.currentframe()
        module = inspect.getmodule(frame)
        assert module is not None
        package_name = module.__name__.split(sep=".", maxsplit=1)[0]
        pretty_print(package_name, title="package_name")
        assert package_name == "tests"

    def test_get_package_name_here_2(self):
        """Get the name of the package containing this module."""
        package_name = __name__.split(".", maxsplit=1)[0]
        pretty_print(package_name, title="package_name")
        assert package_name == "tests"

    def test_get_package_name_func(self):
        package_name = get_package_name()
        pretty_print(package_name, title="package_name")

    def test_get_project_name(self):
        project_name = config_manager.get_project_name()
        pretty_print(project_name, title="project_name")

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("pipelex", "Pipelex"),
            ("first-word-with-dash", "FirstWordWithDash"),
            ("word_with_underscore", "WordWithUnderscore"),
        ],
    )
    def test_cleanup_name_to_pascal_case(self, name: str, expected: str) -> None:
        result = cleanup_name_to_pascal_case(name)
        assert result == expected, f"Expected {expected} but got {result}"
