"""Unit tests for the CSP nonce sentinel constant."""

import re

from pipelex.graph.csp import CSP_NONCE_SENTINEL


class TestCspNonceSentinel:
    """Tests for the CSP_NONCE_SENTINEL constant."""

    def test_sentinel_not_empty(self) -> None:
        """Ensure the sentinel constant is defined and non-empty."""
        assert CSP_NONCE_SENTINEL
        assert len(CSP_NONCE_SENTINEL) > 0

    def test_sentinel_is_safe_for_html_attribute(self) -> None:
        """Ensure the sentinel contains only alphanumeric characters and underscores.

        This guarantees it is safe for embedding in HTML attribute values
        without risk of injection (no quotes, angle brackets, or spaces).
        """
        assert re.fullmatch(r"[A-Za-z0-9_]+", CSP_NONCE_SENTINEL)
