"""Caller information is read off the frame, never off the source file."""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

import pytest

from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import CallerInfoTemplate, LogConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture


def _own_records(caplog: pytest.LogCaptureFixture, *, name: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == name]


class TestCallerInfo:
    @pytest.fixture
    def log_with_caller_info(self) -> Iterator[Log]:
        """A fresh ``Log`` configured with caller info on, torn down so its handler leaves the root logger."""
        from pipelex.system.configuration.config_loader import ConfigLoader  # ruff: ignore[import-outside-top-level]
        from pipelex.tools.misc.toml_utils import load_toml_from_path  # ruff: ignore[import-outside-top-level]

        config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        log_config = LogConfig.model_validate(config_dict["runtime"]["log"]).model_copy(
            update={"is_caller_info_enabled": True, "caller_info_template": CallerInfoTemplate.FUNC_MODULE_LINE},
        )
        fresh = Log()
        fresh.configure(log_config=log_config)
        try:
            yield fresh
        finally:
            fresh.reset()

    def test_caller_info_names_the_function_module_and_line_without_reading_source(
        self,
        log_with_caller_info: Log,
        caplog: pytest.LogCaptureFixture,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch.object(inspect, "getframeinfo", side_effect=AssertionError("no source lookup"))
        with caplog.at_level(logging.INFO):
            log_with_caller_info.info("located")

        (record,) = _own_records(caplog, name=__name__)
        assert record.funcName == "test_caller_info_names_the_function_module_and_line_without_reading_source"
        assert record.getMessage() == f"{record.funcName} {__name__} {record.lineno}: located"
