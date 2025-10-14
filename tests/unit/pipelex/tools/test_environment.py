import os

import pytest
from pytest_mock import MockerFixture

from pipelex.system.environment import (
    EnvVarNotFoundError,
    all_env_vars_are_set,
    any_env_var_is_placeholder,
    get_optional_env,
    get_required_env,
    is_env_var_set,
    set_env,
)
from pipelex.tools.misc.placeholder import PLACEHOLDER_PREFIX, make_placeholder_value


class TestEnvironment:
    def test_get_required_env_success(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"TEST_VAR": "test_value"})
        result = get_required_env("TEST_VAR")
        assert result == "test_value"

    def test_get_required_env_missing_raises_error(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        with pytest.raises(EnvVarNotFoundError, match="Environment variable 'MISSING_VAR' is required but not set"):
            get_required_env("MISSING_VAR")

    def test_get_required_env_empty_string_raises_error(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"EMPTY_VAR": ""})
        with pytest.raises(EnvVarNotFoundError, match="Environment variable 'EMPTY_VAR' is required but not set"):
            get_required_env("EMPTY_VAR")

    def test_get_optional_env_success(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"TEST_VAR": "test_value"})
        result = get_optional_env("TEST_VAR")
        assert result == "test_value"

    def test_get_optional_env_missing_returns_none(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = get_optional_env("MISSING_VAR")
        assert result is None

    def test_get_optional_env_empty_string_returns_empty_string(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"EMPTY_VAR": ""})
        result = get_optional_env("EMPTY_VAR")
        assert result == ""

    def test_set_env_success(self):
        set_env("TEST_SET_VAR", "new_value")
        assert os.environ["TEST_SET_VAR"] == "new_value"

    def test_set_env_overwrites_existing(self):
        os.environ["EXISTING_VAR"] = "old_value"
        set_env("EXISTING_VAR", "new_value")
        assert os.environ["EXISTING_VAR"] == "new_value"

    def test_all_env_vars_are_set_all_keys_present(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"VAR1": "value1", "VAR2": "value2", "VAR3": "value3"})
        result = all_env_vars_are_set(keys=["VAR1", "VAR2", "VAR3"])
        assert result is True

    def test_all_env_vars_are_set_some_keys_missing(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"VAR1": "value1"}, clear=True)
        result = all_env_vars_are_set(keys=["VAR1", "VAR2", "VAR3"])
        assert result is False

    def test_all_env_vars_are_set_all_keys_missing(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = all_env_vars_are_set(keys=["VAR1", "VAR2", "VAR3"])
        assert result is False

    def test_all_env_vars_are_set_empty_iterable(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = all_env_vars_are_set(keys=[])
        assert result is True

    def test_all_env_vars_are_set_single_key_present(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"SINGLE_VAR": "value"})
        result = is_env_var_set(key="SINGLE_VAR")
        assert result is True

    def test_all_env_vars_are_set_single_key_missing(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = is_env_var_set(key="MISSING_VAR")
        assert result is False

    def test_all_env_vars_are_set_empty_string_value_counts_as_set(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"EMPTY_VAR": ""})
        result = is_env_var_set(key="EMPTY_VAR")
        assert result is True

    def test_any_env_var_is_placeholder_has_placeholder(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"VAR1": "real_value", "VAR2": make_placeholder_value("VAR2"), "VAR3": "another_value"})
        result = any_env_var_is_placeholder(["VAR1", "VAR2", "VAR3"])
        assert result is True

    def test_any_env_var_is_placeholder_no_placeholders(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"VAR1": "real_value", "VAR2": "another_value", "VAR3": "third_value"})
        result = any_env_var_is_placeholder(["VAR1", "VAR2", "VAR3"])
        assert result is False

    def test_any_env_var_is_placeholder_all_placeholders(self, mocker: MockerFixture):
        mocker.patch.dict(
            os.environ,
            {
                "VAR1": make_placeholder_value("VAR1"),
                "VAR2": make_placeholder_value("VAR2"),
                "VAR3": make_placeholder_value("VAR3"),
            },
        )
        result = any_env_var_is_placeholder(["VAR1", "VAR2", "VAR3"])
        assert result is True

    def test_any_env_var_is_placeholder_missing_vars_no_placeholder(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"VAR1": "real_value"}, clear=True)
        result = any_env_var_is_placeholder(["VAR1", "MISSING_VAR"])
        assert result is False

    def test_any_env_var_is_placeholder_empty_iterable(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {})
        result = any_env_var_is_placeholder([])
        assert result is False

    def test_any_env_var_is_placeholder_single_placeholder(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"PLACEHOLDER_VAR": make_placeholder_value("PLACEHOLDER_VAR")})
        result = any_env_var_is_placeholder(["PLACEHOLDER_VAR"])
        assert result is True

    def test_any_env_var_is_placeholder_single_non_placeholder(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"NORMAL_VAR": "normal_value"})
        result = any_env_var_is_placeholder(["NORMAL_VAR"])
        assert result is False

    def test_any_env_var_is_placeholder_prefix_at_start_only(self, mocker: MockerFixture):
        """Test that only values starting with the prefix are considered placeholders."""
        mocker.patch.dict(
            os.environ,
            {
                "VAR1": f"not-{PLACEHOLDER_PREFIX}-suffix",
                "VAR2": make_placeholder_value("VAR2"),
            },
        )
        result = any_env_var_is_placeholder(["VAR1"])
        assert result is False
        result = any_env_var_is_placeholder(["VAR2"])
        assert result is True

    def test_any_env_var_is_placeholder_exact_prefix_match(self, mocker: MockerFixture):
        """Test that exact prefix match (without suffix) is also considered a placeholder."""
        mocker.patch.dict(os.environ, {"EXACT_PREFIX": PLACEHOLDER_PREFIX})
        result = any_env_var_is_placeholder(["EXACT_PREFIX"])
        assert result is True

    def test_env_var_not_found_error_inheritance(self):
        error = EnvVarNotFoundError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"
