import base64

import pytest

from pipelex.tools.misc.base64_utils import load_binary_as_base64, load_binary_as_base64_async
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
