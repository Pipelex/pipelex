import os

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.environment import (
    EnvVarNotFoundError,
    get_optional_env,
    get_required_env,
    set_env,
)


class TestGetRequiredEnv:
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


class TestGetOptionalEnv:
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


class TestSetEnv:
    def test_set_env_success(self):
        set_env("TEST_SET_VAR", "new_value")
        assert os.environ["TEST_SET_VAR"] == "new_value"

    def test_set_env_overwrites_existing(self):
        os.environ["EXISTING_VAR"] = "old_value"
        set_env("EXISTING_VAR", "new_value")
        assert os.environ["EXISTING_VAR"] == "new_value"


class TestEnvVarNotFoundError:
    def test_env_var_not_found_error_inheritance(self):
        error = EnvVarNotFoundError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"
