"""Unit tests for copying a file-shaped main output into the results folder."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.run._main_stuff_file import save_main_stuff_file
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _data_url(*, mime_type: str, data: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode()}"


class TestMainStuffFile:
    @pytest.fixture(autouse=True)
    def _no_storage(self, mocker: MockerFixture) -> None:
        # A data URL needs no storage provider, and none is set up in a unit test.
        mocker.patch("pipelex.cli.commands.run._main_stuff_file.get_storage_provider", return_value=None)

    @pytest.mark.asyncio
    async def test_an_image_keeps_its_own_filename(self, tmp_path: Path) -> None:
        image = ImageContent(url=_data_url(mime_type="image/png", data=b"png bytes"), filename="logo.png", mime_type="image/png")

        saved_path = await save_main_stuff_file(content=image, output_dir=tmp_path, reserved_names=frozenset())

        assert saved_path == tmp_path / "logo.png"
        assert (tmp_path / "logo.png").read_bytes() == b"png bytes"

    @pytest.mark.asyncio
    async def test_the_file_never_replaces_an_artifact_of_the_run(self, tmp_path: Path) -> None:
        (tmp_path / "main_stuff.json").write_text("{}", encoding="utf-8")
        passed_through = DocumentContent(url=_data_url(mime_type="application/json", data=b"[]"), filename="MAIN_STUFF.json")

        saved_path = await save_main_stuff_file(content=passed_through, output_dir=tmp_path, reserved_names=frozenset())

        assert saved_path is not None
        assert saved_path.name.casefold() == "main_stuff-1.json"
        assert (tmp_path / "main_stuff.json").read_text(encoding="utf-8") == "{}"

    @pytest.mark.asyncio
    async def test_the_file_never_takes_a_name_the_run_writes_afterwards(self, tmp_path: Path) -> None:
        passed_through = DocumentContent(url=_data_url(mime_type="application/json", data=b"{}"), filename="working_memory.json")

        saved_path = await save_main_stuff_file(content=passed_through, output_dir=tmp_path, reserved_names=frozenset({"working_memory.json"}))

        assert saved_path == tmp_path / "working_memory-1.json"
