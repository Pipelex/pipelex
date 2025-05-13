# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import base64

import pytest

from pipelex.tools.utils.image_utils import load_image_as_base64_from_bytes_async, load_image_as_base64_from_path_async
from tests.tools.test_data import FileHelperTestCases


@pytest.mark.asyncio
async def test_load_image_as_base64_from_bytes_async():
    # Prepare test data
    with open(FileHelperTestCases.TEST_IMAGE, "rb") as image_file:
        test_image_bytes = image_file.read()
    expected_base64 = base64.b64encode(test_image_bytes)

    # Call the function
    result = await load_image_as_base64_from_bytes_async(test_image_bytes)

    # Assert the result
    assert result == expected_base64
    assert isinstance(result, bytes)


@pytest.mark.asyncio
async def test_load_image_as_base64_from_path_async():
    # Call the function
    result = await load_image_as_base64_from_path_async(FileHelperTestCases.TEST_IMAGE)

    # Assert that the result is bytes
    assert isinstance(result, bytes)
