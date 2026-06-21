"""Tests for the F3 HTTP-error-mapper seam: the registrar collects framework-agnostic exc->ErrorReport mappers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.base_exceptions import ErrorReport
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicateHttpErrorMapperError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


class _FakeTransportError(Exception):
    """Stand-in for an orchestrator SDK's transport fault (e.g. temporalio.TemporalError)."""


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _to_report(exc: Exception) -> ErrorReport:
    return ErrorReport(
        error_type="FakeTransportError",
        message=str(exc),
        title="Fake transport error",
        type_uri="https://errors.pipelex.com/fake-transport-error",
        retryable=True,
    )


class TestHttpErrorMapperSeam:
    """A plugin contributes an exc->ErrorReport mapper; the registrar collects it, returns a copy, and fails loud on duplicates."""

    def test_add_and_get_mapper(self) -> None:
        """A registered mapper is returned keyed by its exc_type and produces the classified ErrorReport when invoked."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        registrar.add_http_error_mapper(exc_type=_FakeTransportError, to_error_report=_to_report)

        mappers = registrar.get_http_error_mappers()
        assert set(mappers) == {_FakeTransportError}
        report = mappers[_FakeTransportError](_FakeTransportError("server unreachable"))
        assert report.retryable is True
        assert report.message == "server unreachable"
        assert report.type_uri == "https://errors.pipelex.com/fake-transport-error"

    def test_contribution_is_recorded(self) -> None:
        """Adding a mapper records a contribution line on the active plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        registrar.add_http_error_mapper(exc_type=_FakeTransportError, to_error_report=_to_report)

        assert any("http error mapper" in contribution and "_FakeTransportError" in contribution for contribution in discovery.contributions)

    def test_duplicate_exc_type_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins mapping the same exception type is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_http_error_mapper(exc_type=_FakeTransportError, to_error_report=_to_report)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        with pytest.raises(DuplicateHttpErrorMapperError) as exc_info:
            registrar.add_http_error_mapper(exc_type=_FakeTransportError, to_error_report=_to_report)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert "_FakeTransportError" in exc_info.value.exc_type

    def test_get_returns_a_copy(self) -> None:
        """The accessor hands back a copy, so a consumer cannot mutate the registrar's accumulated state."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_http_error_mapper(exc_type=_FakeTransportError, to_error_report=_to_report)

        snapshot = registrar.get_http_error_mappers()
        snapshot.clear()

        assert registrar.get_http_error_mappers() == {_FakeTransportError: _to_report}

    def test_no_mappers_by_default(self) -> None:
        """A registrar with no contributions exposes an empty mapper set (host wraps nothing)."""
        registrar = _make_registrar()

        assert registrar.get_http_error_mappers() == {}
