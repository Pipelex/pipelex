"""Tests for the F3 HTTP-error-mapper seam: the registrar collects exc->ErrorReport mappers, resolving the exc type lazily (import-light register)."""

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
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


def _to_report(exc: Exception) -> ErrorReport:
    return ErrorReport(
        error_type="FakeTransportError",
        message=str(exc),
        title="Fake transport error",
        type_uri="https://errors.pipelex.com/fake-transport-error",
        retryable=True,
    )


class TestHttpErrorMapperSeam:
    """A plugin contributes an exc->ErrorReport mapper via a lazy exc-type provider; the registrar resolves it on read, fail-loud on dups."""

    def test_add_and_get_mapper(self) -> None:
        """A registered mapper is returned keyed by its resolved exc_type and produces the classified ErrorReport when invoked."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.add_http_error_mapper(exc_type_provider=lambda: _FakeTransportError, to_error_report=_to_report)

        mappers = registrar.get_http_error_mappers()
        assert set(mappers) == {_FakeTransportError}
        report = mappers[_FakeTransportError](_FakeTransportError("server unreachable"))
        assert report.retryable is True
        assert report.message == "server unreachable"
        assert report.type_uri == "https://errors.pipelex.com/fake-transport-error"

    def test_provider_resolved_lazily_not_at_registration(self) -> None:
        """The exc-type provider runs only on get_http_error_mappers (read time), never at register — the import-light invariant."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        resolutions: list[int] = []

        def _provider() -> type[Exception]:
            resolutions.append(1)
            return _FakeTransportError

        registrar.add_http_error_mapper(exc_type_provider=_provider, to_error_report=_to_report)
        assert resolutions == []  # registration must not have called the provider

        resolved = registrar.get_http_error_mappers()
        assert resolutions == [1]  # resolution happens only on read
        assert set(resolved) == {_FakeTransportError}

    def test_contribution_is_recorded_without_resolving(self) -> None:
        """Adding a mapper records a contribution line on the active plugin's discovery — and does so without resolving the exc type."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        def _exploding_provider() -> type[Exception]:
            pytest.fail("provider must not run at registration")

        registrar.add_http_error_mapper(exc_type_provider=_exploding_provider, to_error_report=_to_report)

        assert "http error mapper" in discovery.contributions

    def test_duplicate_exc_type_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins resolving to the same exception type is a fail-loud conflict naming both — detected at resolution time."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_http_error_mapper(exc_type_provider=lambda: _FakeTransportError, to_error_report=_to_report)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_http_error_mapper(exc_type_provider=lambda: _FakeTransportError, to_error_report=_to_report)

        with pytest.raises(DuplicateHttpErrorMapperError) as exc_info:
            registrar.get_http_error_mappers()

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert "_FakeTransportError" in exc_info.value.exc_type

    def test_get_returns_a_fresh_dict(self) -> None:
        """The accessor hands back a freshly built dict, so a consumer cannot mutate the registrar's accumulated state."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_http_error_mapper(exc_type_provider=lambda: _FakeTransportError, to_error_report=_to_report)

        snapshot = registrar.get_http_error_mappers()
        snapshot.clear()

        assert registrar.get_http_error_mappers() == {_FakeTransportError: _to_report}

    def test_no_mappers_by_default(self) -> None:
        """A registrar with no contributions exposes an empty mapper set (host wraps nothing, resolves nothing)."""
        registrar = _make_registrar()

        assert registrar.get_http_error_mappers() == {}
