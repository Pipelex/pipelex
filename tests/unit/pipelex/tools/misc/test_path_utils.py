import os

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.path_utils import (
    InterpretedPathOrUrl,
    clarify_path_or_url,
    interpret_path_or_url,
)


class TestInterpretedPathOrUrl:
    def test_enum_values(self):
        assert InterpretedPathOrUrl.FILE_URI == "file_uri"
        assert InterpretedPathOrUrl.FILE_PATH == "file_path"
        assert InterpretedPathOrUrl.URL == "uri"
        assert InterpretedPathOrUrl.FILE_NAME == "file_name"
        assert InterpretedPathOrUrl.BASE_64 == "base_64"

    def test_desc_property_file_uri(self):
        assert InterpretedPathOrUrl.FILE_URI.desc == "File URI"

    def test_desc_property_file_path(self):
        assert InterpretedPathOrUrl.FILE_PATH.desc == "File Path"

    def test_desc_property_url(self):
        assert InterpretedPathOrUrl.URL.desc == "URL"

    def test_desc_property_file_name(self):
        assert InterpretedPathOrUrl.FILE_NAME.desc == "File Name"

    def test_desc_property_base_64(self):
        assert InterpretedPathOrUrl.BASE_64.desc == "Base 64"


class TestInterpretPathOrUrl:
    def test_interpret_file_uri(self):
        result = interpret_path_or_url("file:///home/user/file.txt")
        assert result == InterpretedPathOrUrl.FILE_URI

    def test_interpret_file_uri_windows(self):
        result = interpret_path_or_url("file:///C:/Users/user/file.txt")
        assert result == InterpretedPathOrUrl.FILE_URI

    def test_interpret_http_url(self):
        result = interpret_path_or_url("http://example.com")
        assert result == InterpretedPathOrUrl.URL

    def test_interpret_https_url(self):
        result = interpret_path_or_url("https://example.com/path")
        assert result == InterpretedPathOrUrl.URL

    def test_interpret_absolute_file_path_unix(self):
        result = interpret_path_or_url("/home/user/file.txt")
        assert result == InterpretedPathOrUrl.FILE_PATH

    def test_interpret_relative_file_path_unix(self):
        result = interpret_path_or_url("user/file.txt")
        assert result == InterpretedPathOrUrl.FILE_PATH

    def test_interpret_absolute_file_path_windows_style(self):
        # Test with actual Windows-style paths (backslashes)
        # On Unix systems, backslashes aren't recognized as path separators
        result = interpret_path_or_url("C:\\Users\\user\\file.txt")
        assert result == InterpretedPathOrUrl.FILE_NAME

    def test_interpret_relative_file_path_windows_style(self):
        # Test with actual Windows-style paths (backslashes)
        # On Unix systems, backslashes aren't recognized as path separators
        result = interpret_path_or_url("user\\file.txt")
        assert result == InterpretedPathOrUrl.FILE_NAME

    def test_interpret_path_with_current_os_separator(self, mocker: MockerFixture):
        # Test with the current OS path separator

        path_with_sep = f"user{os.sep}file.txt"
        result = interpret_path_or_url(path_with_sep)
        assert result == InterpretedPathOrUrl.FILE_PATH

    def test_interpret_file_name_only(self):
        result = interpret_path_or_url("file.txt")
        assert result == InterpretedPathOrUrl.FILE_NAME

    def test_interpret_file_name_no_extension(self):
        result = interpret_path_or_url("filename")
        assert result == InterpretedPathOrUrl.FILE_NAME

    def test_interpret_empty_string(self):
        result = interpret_path_or_url("")
        assert result == InterpretedPathOrUrl.FILE_NAME

    def test_interpret_edge_case_http_in_path(self):
        result = interpret_path_or_url("/path/to/http_file.txt")
        assert result == InterpretedPathOrUrl.FILE_PATH

    def test_interpret_edge_case_file_in_url(self):
        result = interpret_path_or_url("http://example.com/file.txt")
        assert result == InterpretedPathOrUrl.URL


class TestClarifyPathOrUrl:
    def test_clarify_file_uri_unix(self):
        file_path, url = clarify_path_or_url("file:///home/user/file.txt")
        assert file_path == "/home/user/file.txt"
        assert url is None

    def test_clarify_file_uri_windows(self):
        file_path, url = clarify_path_or_url("file:///C:/Users/user/file.txt")
        assert file_path == "/C:/Users/user/file.txt"
        assert url is None

    def test_clarify_file_uri_with_spaces(self) -> None:
        file_path, url = clarify_path_or_url("file:///home/user/my%20file.txt")
        assert file_path == "/home/user/my file.txt"
        assert url is None

    def test_clarify_file_uri_with_special_chars(self):
        file_path, url = clarify_path_or_url("file:///home/user/file%20%26%20more.txt")
        assert file_path == "/home/user/file & more.txt"
        assert url is None

    def test_clarify_http_url(self):
        file_path, url = clarify_path_or_url("http://example.com")
        assert file_path is None
        assert url == "http://example.com"

    def test_clarify_https_url(self):
        file_path, url = clarify_path_or_url("https://example.com/path/to/file")
        assert file_path is None
        assert url == "https://example.com/path/to/file"

    def test_clarify_absolute_file_path(self):
        file_path, url = clarify_path_or_url("/home/user/file.txt")
        assert file_path == "/home/user/file.txt"
        assert url is None

    def test_clarify_relative_file_path(self):
        file_path, url = clarify_path_or_url("user/file.txt")
        assert file_path == "user/file.txt"
        assert url is None

    def test_clarify_file_name_only(self):
        file_path, url = clarify_path_or_url("file.txt")
        assert file_path == "file.txt"
        assert url is None

    def test_clarify_empty_string(self):
        file_path, url = clarify_path_or_url("")
        assert file_path == ""
        assert url is None

    def test_clarify_base_64_raises_not_implemented(self, mocker: MockerFixture):
        # Mock interpret_path_or_url to return BASE_64
        mocker.patch(
            "pipelex.tools.misc.path_utils.interpret_path_or_url",
            return_value=InterpretedPathOrUrl.BASE_64,
        )
        with pytest.raises(NotImplementedError, match="Base 64 is not supported yet by clarify_path_or_url"):
            clarify_path_or_url("some_base64_data")

    def test_clarify_uses_interpret_path_or_url(self, mocker: MockerFixture):
        mock_interpret = mocker.patch(
            "pipelex.tools.misc.path_utils.interpret_path_or_url",
            return_value=InterpretedPathOrUrl.FILE_PATH,
        )

        clarify_path_or_url("/test/path")

        mock_interpret.assert_called_once_with("/test/path")

    def test_clarify_urlparse_called_for_file_uri(self, mocker: MockerFixture):
        mock_urlparse = mocker.patch("urllib.parse.urlparse")
        mock_urlparse.return_value.path = "/home/user/file.txt"
        mock_unquote = mocker.patch("urllib.parse.unquote", return_value="/home/user/file.txt")

        mocker.patch(
            "pipelex.tools.misc.path_utils.interpret_path_or_url",
            return_value=InterpretedPathOrUrl.FILE_URI,
        )

        file_path, url = clarify_path_or_url("file:///home/user/file.txt")

        mock_urlparse.assert_called_once_with("file:///home/user/file.txt")
        mock_unquote.assert_called_once_with("/home/user/file.txt")
        assert file_path == "/home/user/file.txt"
        assert url is None
