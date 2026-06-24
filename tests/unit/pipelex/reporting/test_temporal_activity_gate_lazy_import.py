"""Lazy-import contract of the Temporal-activity gate in ``reporting_manager``.

``_is_in_temporal_activity`` must detect the activity context WITHOUT importing temporalio:
a module-level import would put the entire temporalio extra (Rust bridge, protobuf, ~130ms)
on every pipelex boot's critical path wherever ``pipelex-temporal`` is installed — including
processes that never touch Temporal (CLI validate runs, direct-mode servers, the hosted
runner image). The gate sniffs ``sys.modules`` instead: a process that never imported
``temporalio.activity`` cannot be inside a Temporal activity, because the activity context is
set by temporalio's own machinery, which requires the module to be imported.
"""

import subprocess  # noqa: S404
import sys

import pytest
from pytest_mock import MockerFixture

from pipelex.reporting.reporting_manager import _is_in_temporal_activity  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]


class TestTemporalActivityGateLazyImport:
    def test_false_when_temporalio_activity_not_imported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No ``temporalio.activity`` in ``sys.modules`` → no activity context can exist."""
        monkeypatch.delitem(sys.modules, "temporalio.activity", raising=False)
        assert _is_in_temporal_activity() is False

    def test_delegates_to_in_activity_when_module_present(self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
        """With ``temporalio.activity`` imported, the gate delegates to its ``in_activity()``."""
        fake_activity_module = mocker.MagicMock()
        fake_activity_module.in_activity.return_value = True
        monkeypatch.setitem(sys.modules, "temporalio.activity", fake_activity_module)
        assert _is_in_temporal_activity() is True
        fake_activity_module.in_activity.assert_called_once_with()

        fake_activity_module.in_activity.return_value = False
        assert _is_in_temporal_activity() is False

    def test_importing_reporting_manager_does_not_import_temporalio(self) -> None:
        """Boot-cost guard: the module import must not pull temporalio into ``sys.modules``.

        Subprocess check so the assertion sees a pristine interpreter (the test process
        itself may have temporalio loaded via the integration fixtures).
        """
        probe = "import sys; import pipelex.reporting.reporting_manager; raise SystemExit(2 if 'temporalio' in sys.modules else 0)"
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"importing pipelex.reporting.reporting_manager pulled temporalio into sys.modules (exit {result.returncode}); stderr: {result.stderr}"
        )
