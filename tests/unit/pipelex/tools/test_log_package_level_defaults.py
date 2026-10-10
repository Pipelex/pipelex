from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

    from pipelex.tools.log.log_config import LogConfig

pytestmark = pytest.mark.usefixtures("no_pipelex_home")

PROJECT_FILE_AT_DEBUG = """\
[runtime.log]
default_log_level = "DEBUG"
"""

STDLIB_LEVELS = (LOGGING_LEVEL_VERBOSE, logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)

REQUEST_LINE = 'HTTP Request: POST https://endpoint.invalid/openai/responses?api-version=preview "HTTP/1.1 200 OK"'


def _boot_log_config(*, tmp_path: Path, mocker: MockerFixture, project_file_text: str | None) -> LogConfig:
    """The log configuration the boot's loader reads for an empty home and a project holding at most ``project_file_text``.

    The home and the project are faked so that no configuration of the machine running the tests takes part.
    """
    fake_home = tmp_path / "home"
    (fake_home / ".pipelex").mkdir(parents=True)
    project_root = tmp_path / "project"
    (project_root / ".git").mkdir(parents=True)
    if project_file_text is not None:
        project_config_dir = project_root / ".pipelex"
        project_config_dir.mkdir()
        (project_config_dir / "pipelex.toml").write_text(project_file_text, encoding="utf-8")
    mocker.patch.object(Path, "home", return_value=fake_home)
    mocker.patch.object(Path, "cwd", return_value=project_root)
    return ConfigLoader().load_config_validated(config_cls=PipelexConfig).runtime.log


@contextmanager
def _configured_as_the_boot_does(*, log_config: LogConfig) -> Generator[None]:
    """``configure`` on a fresh ``Log``, with the handler it installs and every logger level it sets put back afterwards."""
    touched_logger_names = ["", *(package_name.replace("-", ".") for package_name in log_config.package_log_levels)]
    saved_levels = {logger_name: logging.getLogger(logger_name).level for logger_name in touched_logger_names}
    fresh_log = Log()
    fresh_log.configure(log_config=log_config)
    try:
        yield
    finally:
        fresh_log.reset()
        for logger_name, saved_level in saved_levels.items():
            logging.getLogger(logger_name).setLevel(saved_level)


def _levels_passed_by(*, logger_name: str) -> list[int]:
    logger = logging.getLogger(logger_name)
    return [level for level in STDLIB_LEVELS if logger.isEnabledFor(level)]


class TestHttpClientForkLogLevels:
    @pytest.mark.parametrize(
        "project_file_text",
        [None, PROJECT_FILE_AT_DEBUG],
        ids=["shipped-default-level", "default-level-debug"],
    )
    @pytest.mark.parametrize(
        ("fork_name", "original_name"),
        [
            ("httpx2", "httpx"),
            ("httpcore2", "httpcore"),
        ],
    )
    def test_a_fork_passes_exactly_the_levels_its_original_passes(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        project_file_text: str | None,
        fork_name: str,
        original_name: str,
    ) -> None:
        """The forks openai 3.x logs through, httpx2 and httpcore2, must log what httpx and httpcore log.

        Checked at the shipped default level and with the default opened to DEBUG, where an unpinned fork would follow the root.
        """
        log_config = _boot_log_config(tmp_path=tmp_path, mocker=mocker, project_file_text=project_file_text)

        with _configured_as_the_boot_does(log_config=log_config):
            passed_by_fork = _levels_passed_by(logger_name=fork_name)
            passed_by_original = _levels_passed_by(logger_name=original_name)

        assert passed_by_fork == passed_by_original

    def test_httpx2_drops_the_request_line_of_an_inference_call(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The line httpx2 logs per request, at INFO with the provider's endpoint in it, emits no record; a warning would still pass.

        The capture is opened at INFO, the root level the boot sets, so an unpinned httpx2 would be captured.
        """
        log_config = _boot_log_config(tmp_path=tmp_path, mocker=mocker, project_file_text=None)

        with _configured_as_the_boot_does(log_config=log_config), caplog.at_level(logging.INFO):
            httpx2_logger = logging.getLogger("httpx2")
            httpx2_logger.info(REQUEST_LINE)
            passes_warnings = httpx2_logger.isEnabledFor(logging.WARNING)

        assert [record for record in caplog.records if record.name == "httpx2"] == []
        assert passes_warnings
