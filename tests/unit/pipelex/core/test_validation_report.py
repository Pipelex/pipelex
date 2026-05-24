"""Unit tests for report_validation_error — runs before/around bootstrap.

Pins the regression where ``log.verbose`` raised ``RuntimeError("LogConfig is not set")``
inside ``report_validation_error`` because the doctor calls this helper from inside its
own bootstrap (setup_config raised, hub._config still None, log not configured). The
fix dropped the now-unnecessary log.verbose calls and replaced the broad
``try/except RuntimeError`` around ``get_config().migration`` with non-raising hub
accessors. This test pins both behaviors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.core.validation import report_validation_error
from pipelex.hub import PipelexHub

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _ConfigShape(BaseModel):
    required_field: str


def _make_validation_error() -> ValidationError:
    try:
        _ConfigShape.model_validate({})
    except ValidationError as exc:
        return exc
    pytest.fail("Expected _ConfigShape.model_validate to raise ValidationError")


class TestReportValidationError:
    def test_returns_message_without_bootstrap(self, mocker: MockerFixture) -> None:
        """No hub, no log.configure — must still produce the friendly translation.

        Reproduces the agent doctor's pre-fix crash path: with the new ordering,
        check_config_files calls report_validation_error before setup_doctor_runtime,
        so neither the hub nor the log are configured at this point.
        """
        # Ensure the hub singleton is None for this test — mirrors a fresh process
        # where Pipelex.make hasn't run yet.
        mocker.patch.object(PipelexHub, "_instance", None)

        validation_error = _make_validation_error()
        report = report_validation_error(category="config", validation_error=validation_error)

        assert "required_field" in report

    def test_returns_message_when_hub_has_no_config(self, mocker: MockerFixture) -> None:
        """Hub exists but _config is None (setup_config raised mid-flight).

        get_optional_config() returns None; migration hints are omitted; the error
        translation still flows.
        """
        hub_without_config = PipelexHub()
        mocker.patch.object(PipelexHub, "_instance", hub_without_config)

        validation_error = _make_validation_error()
        report = report_validation_error(category="config", validation_error=validation_error)

        assert "required_field" in report
