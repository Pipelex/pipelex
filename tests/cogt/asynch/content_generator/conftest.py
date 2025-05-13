# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import AsyncGenerator

import pytest_asyncio
from pytest import FixtureRequest
from rich import print

from pipelex.cogt.content_generation.content_generator import ContentGenerator


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def content_generator(request: FixtureRequest) -> AsyncGenerator[ContentGenerator, None]:
    # Code to run before each test
    print("\n[magenta]ContentGenerator setup[/magenta]")
    content_generator = ContentGenerator()
    # Return it for use in tests
    yield content_generator
    # Code to run after each test
    print("\n[magenta]ContentGenerator teardown[/magenta]")
