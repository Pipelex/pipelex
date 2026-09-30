"""Unit tests for ERROR_DISCLOSURE env var resolution."""

import pytest
from pipelex.base_exceptions import DisclosureMode

from api.disclosure import ERROR_DISCLOSURE_ENV_VAR, InvalidErrorDisclosureError, resolve_disclosure_mode


class TestDisclosure:
    def test_defaults_to_verbose_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv(ERROR_DISCLOSURE_ENV_VAR, raising=False)
        assert resolve_disclosure_mode() is DisclosureMode.VERBOSE

    @pytest.mark.parametrize("raw", ["", "   ", "\t"])
    def test_blank_value_defaults_to_verbose(self, monkeypatch: pytest.MonkeyPatch, raw: str):
        # An empty or whitespace-only value is treated the same as unset — never
        # rejected as invalid.
        monkeypatch.setenv(ERROR_DISCLOSURE_ENV_VAR, raw)
        assert resolve_disclosure_mode() is DisclosureMode.VERBOSE

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("verbose", DisclosureMode.VERBOSE),
            ("strict", DisclosureMode.STRICT),
            ("STRICT", DisclosureMode.STRICT),
            ("  Verbose  ", DisclosureMode.VERBOSE),
        ],
    )
    def test_resolves_valid_values(self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: DisclosureMode):
        monkeypatch.setenv(ERROR_DISCLOSURE_ENV_VAR, raw)
        assert resolve_disclosure_mode() is expected

    @pytest.mark.parametrize("raw", ["loud", "quiet", "true", "0", "verbos"])
    def test_rejects_unknown_value(self, monkeypatch: pytest.MonkeyPatch, raw: str):
        monkeypatch.setenv(ERROR_DISCLOSURE_ENV_VAR, raw)
        with pytest.raises(InvalidErrorDisclosureError):
            resolve_disclosure_mode()
