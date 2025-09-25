import base64
import binascii
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.filetype_utils import (
    FileType,
    FileTypeException,
    detect_file_type_from_base64,
    detect_file_type_from_bytes,
    detect_file_type_from_path,
)


class TestFileType:
    def test_file_type_creation(self):
        file_type = FileType(extension="jpg", mime="image/jpeg")
        assert file_type.extension == "jpg"
        assert file_type.mime == "image/jpeg"

    def test_file_type_pydantic_validation(self):
        # Test that FileType is a proper Pydantic model
        data = {"extension": "png", "mime": "image/png"}
        file_type = FileType(**data)
        assert file_type.extension == "png"
        assert file_type.mime == "image/png"


class TestFileTypeException:
    def test_file_type_exception_inheritance(self):
        error = FileTypeException("test message")
        assert isinstance(error, Exception)
        assert str(error) == "test message"


class TestDetectFileTypeFromPath:
    def test_detect_file_type_from_path_success_string(self, mocker: MockerFixture):
        # Mock the filetype.guess function
        mock_kind = mocker.MagicMock()
        mock_kind.extension = "jpg"
        mock_kind.mime = "image/jpeg"
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=mock_kind)

        result = detect_file_type_from_path("/path/to/image.jpg")

        assert isinstance(result, FileType)
        assert result.extension == "jpg"
        assert result.mime == "image/jpeg"
        mock_filetype_guess.assert_called_once_with("/path/to/image.jpg")

    def test_detect_file_type_from_path_success_pathlib(self, mocker: MockerFixture):
        # Mock the filetype.guess function
        mock_kind = mocker.MagicMock()
        mock_kind.extension = "png"
        mock_kind.mime = "image/png"
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=mock_kind)

        path = Path("/path/to/image.png")
        result = detect_file_type_from_path(path)

        assert isinstance(result, FileType)
        assert result.extension == "png"
        assert result.mime == "image/png"
        mock_filetype_guess.assert_called_once_with(path)

    def test_detect_file_type_from_path_failure(self, mocker: MockerFixture):
        # Mock filetype.guess to return None (unrecognized file type)
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=None)

        with pytest.raises(FileTypeException, match="Could not identify file type of '/unknown/file.xyz'"):
            detect_file_type_from_path("/unknown/file.xyz")

        mock_filetype_guess.assert_called_once_with("/unknown/file.xyz")

    def test_detect_file_type_from_path_failure_pathlib(self, mocker: MockerFixture):
        # Mock filetype.guess to return None (unrecognized file type)
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=None)

        path = Path("/unknown/file.xyz")
        with pytest.raises(FileTypeException, match="Could not identify file type of '/unknown/file.xyz'"):
            detect_file_type_from_path(path)

        mock_filetype_guess.assert_called_once_with(path)


class TestDetectFileTypeFromBytes:
    def test_detect_file_type_from_bytes_success(self, mocker: MockerFixture):
        # Mock the filetype.guess function
        mock_kind = mocker.MagicMock()
        mock_kind.extension = "pdf"
        mock_kind.mime = "application/pdf"
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=mock_kind)

        test_bytes = b"\x25\x50\x44\x46"  # PDF header
        result = detect_file_type_from_bytes(test_bytes)

        assert isinstance(result, FileType)
        assert result.extension == "pdf"
        assert result.mime == "application/pdf"
        mock_filetype_guess.assert_called_once_with(test_bytes)

    def test_detect_file_type_from_bytes_failure(self, mocker: MockerFixture):
        # Mock filetype.guess to return None (unrecognized file type)
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=None)

        test_bytes = b"unknown file content"
        with pytest.raises(FileTypeException, match="Could not identify file type of given bytes: b'unknown file content'"):
            detect_file_type_from_bytes(test_bytes)

        mock_filetype_guess.assert_called_once_with(test_bytes)

    def test_detect_file_type_from_bytes_failure_long_bytes(self, mocker: MockerFixture):
        # Mock filetype.guess to return None and test truncation of long bytes in error message
        mock_filetype_guess = mocker.patch("filetype.guess", return_value=None)

        # Create bytes longer than 300 characters to test truncation
        test_bytes = b"a" * 350
        with pytest.raises(FileTypeException) as exc_info:
            detect_file_type_from_bytes(test_bytes)

        # Check that the error message contains truncated bytes (first 300 chars)
        error_message = str(exc_info.value)
        assert "Could not identify file type of given bytes:" in error_message
        assert len(error_message) < len(f"Could not identify file type of given bytes: {test_bytes!r}")
        mock_filetype_guess.assert_called_once_with(test_bytes)


class TestDetectFileTypeFromBase64:
    def test_detect_file_type_from_base64_string_success(self, mocker: MockerFixture):
        # Mock detect_file_type_from_bytes
        mock_detect_bytes = mocker.patch(
            "pipelex.tools.misc.filetype_utils.detect_file_type_from_bytes", return_value=FileType(extension="gif", mime="image/gif"),
        )

        # GIF header encoded in base64
        gif_bytes = b"GIF89a"
        b64_string = base64.b64encode(gif_bytes).decode("ascii")

        result = detect_file_type_from_base64(b64_string)

        assert isinstance(result, FileType)
        assert result.extension == "gif"
        assert result.mime == "image/gif"
        mock_detect_bytes.assert_called_once_with(buf=gif_bytes)

    def test_detect_file_type_from_base64_bytes_success(self, mocker: MockerFixture):
        # Mock detect_file_type_from_bytes
        mock_detect_bytes = mocker.patch(
            "pipelex.tools.misc.filetype_utils.detect_file_type_from_bytes", return_value=FileType(extension="jpg", mime="image/jpeg"),
        )

        # JPEG header encoded in base64
        jpeg_bytes = b"\xff\xd8\xff"
        b64_bytes = base64.b64encode(jpeg_bytes)

        result = detect_file_type_from_base64(b64_bytes)

        assert isinstance(result, FileType)
        assert result.extension == "jpg"
        assert result.mime == "image/jpeg"
        mock_detect_bytes.assert_called_once_with(buf=jpeg_bytes)

    def test_detect_file_type_from_base64_data_url_success(self, mocker: MockerFixture):
        # Mock detect_file_type_from_bytes
        mock_detect_bytes = mocker.patch(
            "pipelex.tools.misc.filetype_utils.detect_file_type_from_bytes", return_value=FileType(extension="png", mime="image/png"),
        )

        # PNG header encoded in base64
        png_bytes = b"\x89PNG\r\n\x1a\n"
        b64_data = base64.b64encode(png_bytes).decode("ascii")
        data_url = f"data:image/png;base64,{b64_data}"

        result = detect_file_type_from_base64(data_url)

        assert isinstance(result, FileType)
        assert result.extension == "png"
        assert result.mime == "image/png"
        mock_detect_bytes.assert_called_once_with(buf=png_bytes)

    def test_detect_file_type_from_base64_data_url_with_whitespace(self, mocker: MockerFixture):
        # Mock detect_file_type_from_bytes
        mock_detect_bytes = mocker.patch(
            "pipelex.tools.misc.filetype_utils.detect_file_type_from_bytes", return_value=FileType(extension="txt", mime="text/plain"),
        )

        test_bytes = b"hello world"
        b64_data = base64.b64encode(test_bytes).decode("ascii")
        # Note: The function strips leading whitespace but not trailing whitespace after comma
        data_url_with_whitespace = f"   data:text/plain;base64,{b64_data}"

        result = detect_file_type_from_base64(data_url_with_whitespace)

        assert isinstance(result, FileType)
        assert result.extension == "txt"
        assert result.mime == "text/plain"
        mock_detect_bytes.assert_called_once_with(buf=test_bytes)

    def test_detect_file_type_from_base64_invalid_base64_string(self, mocker: MockerFixture):
        # Test with invalid base64 string
        invalid_b64 = "invalid!base64!string!"

        with pytest.raises(FileTypeException, match="Could not identify file type of given bytes because input is not valid Base-64"):
            detect_file_type_from_base64(invalid_b64)

    def test_detect_file_type_from_base64_invalid_base64_bytes(self, mocker: MockerFixture):
        # Test with invalid base64 bytes
        invalid_b64_bytes = b"invalid!base64!bytes!"

        with pytest.raises(FileTypeException, match="Could not identify file type of given bytes because input is not valid Base-64"):
            detect_file_type_from_base64(invalid_b64_bytes)

    def test_detect_file_type_from_base64_data_url_no_comma(self, mocker: MockerFixture):
        # Test data URL without comma (should be treated as regular base64)
        mocker.patch(
            "pipelex.tools.misc.filetype_utils.detect_file_type_from_bytes", return_value=FileType(extension="bin", mime="application/octet-stream"),
        )

        # This will be treated as a base64 string since there's no comma
        no_comma_url = "data:image/png;base64somedata"
        # base64 decode will likely fail, but let's mock it working for testing
        mocker.patch("base64.b64decode", return_value=b"test")

        result = detect_file_type_from_base64(no_comma_url)

        assert isinstance(result, FileType)
        assert result.extension == "bin"
        assert result.mime == "application/octet-stream"

    def test_detect_file_type_from_base64_binascii_error_chain(self, mocker: MockerFixture):
        # Test that binascii.Error is properly chained when base64 decode fails
        mocker.patch("base64.b64decode", side_effect=binascii.Error("Invalid base64"))

        with pytest.raises(FileTypeException) as exc_info:
            detect_file_type_from_base64("invalid")

        # Check that the original exception is chained
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, binascii.Error)
        assert str(exc_info.value.__cause__) == "Invalid base64"
