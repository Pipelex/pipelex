"""`interpreter.scan.excluded_dirs` is an array of directory names, read as a set; any other value is refused.

A string here used to be read as the set of its letters.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.system.configuration.configs import ScanConfig


class TestScanConfigExcludedDirs:
    @pytest.mark.parametrize("value", [["node_modules", ".venv"], ("node_modules", ".venv"), frozenset({"node_modules", ".venv"})])
    def test_a_list_of_names_is_read_as_a_set(self, value: Any) -> None:
        assert ScanConfig.model_validate({"excluded_dirs": value}).excluded_dirs == frozenset({"node_modules", ".venv"})

    @pytest.mark.parametrize("value", [pytest.param("node_modules", id="a_string"), pytest.param(5, id="an_integer")])
    def test_a_value_that_is_not_a_list_is_refused(self, value: Any) -> None:
        with pytest.raises(ValidationError, match="Input should be a valid frozenset"):
            ScanConfig.model_validate({"excluded_dirs": value})
