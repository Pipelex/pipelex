import base64
from pathlib import Path

import pytest

from pipelex.tools.misc.base_64_utils import (
    encode_to_base64,
    encode_to_base64_async,
    load_binary_as_base64,
    load_binary_as_base64_async,
    save_base_64_str_to_binary_file,
)
from tests.cases import FileHelperTestCases


class TestBase64Utils:
    def test_load_binary_as_base64(self) -> None:
        file_path = FileHelperTestCases.TEST_IMAGE
        with open(file_path, "rb") as f:
            expected = base64.b64encode(f.read())

        result = load_binary_as_base64(path=file_path)

        assert result == expected

    @pytest.mark.asyncio
    async def test_load_binary_as_base64_async(self) -> None:
        file_path = FileHelperTestCases.TEST_IMAGE
        with open(file_path, "rb") as f:
            expected = base64.b64encode(f.read())

        result = await load_binary_as_base64_async(path=file_path)

        assert result == expected

    def test_encode_to_base64(self) -> None:
        data = b"hello world"
        expected = base64.b64encode(data)

        assert encode_to_base64(data) == expected

    @pytest.mark.asyncio
    async def test_encode_to_base64_async(self) -> None:
        data = b"async data"
        expected = base64.b64encode(data)

        result = await encode_to_base64_async(data)

        assert result == expected

    def test_save_base64_to_binary_file_plain(self, tmp_path: Path) -> None:
        data = b"binary data"
        b64 = base64.b64encode(data).decode()
        out_file = tmp_path / "out.bin"

        save_base_64_str_to_binary_file(base_64_str=b64, file_path=str(out_file))

        with open(out_file, "rb") as f:
            assert f.read() == data

    def test_save_base64_to_binary_file_data_url(self, tmp_path: Path) -> None:
        data = b"more data"
        b64 = base64.b64encode(data).decode()
        data_url = f"data:application/octet-stream;base64,{b64}"
        out_file = tmp_path / "out.bin"

        save_base_64_str_to_binary_file(base_64_str=data_url, file_path=str(out_file))

        with open(out_file, "rb") as f:
            assert f.read() == data
