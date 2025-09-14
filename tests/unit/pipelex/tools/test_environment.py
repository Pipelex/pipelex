import os

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.environment import (
    EnvVarNotFoundError,
    get_env_rooted_path,
    get_optional_env,
    get_required_env,
    get_rooted_path,
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


class TestGetRootedPath:
    def test_get_rooted_path_none_path(self):
        result = get_rooted_path("/root")
        assert result == "/root"

    def test_get_rooted_path_empty_path(self):
        result = get_rooted_path("/root", "")
        assert result == "/root"

    def test_get_rooted_path_already_starts_with_root(self):
        result = get_rooted_path("/root", "/root/subdir")
        assert result == "/root/subdir"

    def test_get_rooted_path_absolute_path_different_root(self):
        result = get_rooted_path("/root", "/other/absolute/path")
        assert result == "/other/absolute/path"

    def test_get_rooted_path_relative_path(self):
        result = get_rooted_path("/root", "relative/path")
        assert result == "/root/relative/path"

    def test_get_rooted_path_removes_trailing_slash(self):
        result = get_rooted_path("/root", "subdir/")
        assert result == "/root/subdir"

    def test_get_rooted_path_keeps_root_without_trailing_slash(self):
        result = get_rooted_path("/root/", "")
        assert result == "/root"

    def test_get_rooted_path_absolute_check(self, mocker: MockerFixture):
        mock_isabs = mocker.patch("os.path.isabs", return_value=True)
        result = get_rooted_path("/root", "fake/absolute")
        assert result == "fake/absolute"
        mock_isabs.assert_called_once_with("fake/absolute")

    def test_get_rooted_path_join_called(self, mocker: MockerFixture):
        mock_join = mocker.patch("os.path.join", return_value="/root/relative")
        mocker.patch("os.path.isabs", return_value=False)
        result = get_rooted_path("/root", "relative")
        assert result == "/root/relative"
        mock_join.assert_called_once_with("/root", "relative")


class TestGetEnvRootedPath:
    def test_get_env_rooted_path_with_env_var(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"ROOT_ENV": "/env/root"})
        result = get_env_rooted_path("ROOT_ENV", "subdir")
        assert result == "/env/root/subdir"

    def test_get_env_rooted_path_missing_env_var(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {}, clear=True)
        result = get_env_rooted_path("MISSING_ROOT_ENV", "subdir")
        assert result == "subdir"

    def test_get_env_rooted_path_empty_env_var(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"EMPTY_ROOT_ENV": ""})
        result = get_env_rooted_path("EMPTY_ROOT_ENV", "subdir")
        assert result == "subdir"

    def test_get_env_rooted_path_none_path(self, mocker: MockerFixture):
        mocker.patch.dict(os.environ, {"ROOT_ENV": "/env/root"})
        result = get_env_rooted_path("ROOT_ENV")
        assert result == "/env/root"


class TestEnvVarNotFoundError:
    def test_env_var_not_found_error_inheritance(self):
        error = EnvVarNotFoundError("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"
