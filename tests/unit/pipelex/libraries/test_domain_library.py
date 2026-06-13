import logging

import pytest

from pipelex.core.domains.domain import Domain
from pipelex.libraries.domain.domain_library import DomainLibrary


class TestDomainLibrary:
    """Tests for DomainLibrary domain management."""

    def test_add_domain_idempotent(self):
        """Adding the same domain twice does not raise — idempotent for multi-bundle loading."""
        library = DomainLibrary.make_empty()
        domain = Domain(code="scoring", description="Scoring domain")
        library.add_domain(domain=domain)
        library.add_domain(domain=domain)
        assert len(library.root) == 1
        assert library.get_domain("scoring") is domain

    def test_add_different_domains(self):
        """Adding two different domains stores both."""
        library = DomainLibrary.make_empty()
        domain_scoring = Domain(code="scoring", description="Scoring domain")
        domain_analytics = Domain(code="analytics", description="Analytics domain")
        library.add_domain(domain=domain_scoring)
        library.add_domain(domain=domain_analytics)
        assert len(library.root) == 2
        assert library.get_domain("scoring") is domain_scoring
        assert library.get_domain("analytics") is domain_analytics

    @pytest.mark.parametrize(
        "domains",
        [
            # Root header first, then the membership-only sibling.
            [Domain(code="meta", description="Meta domain", system_prompt="You are a meta assistant."), Domain(code="meta")],
            # Sibling first (no metadata): the root must still win — order-independent.
            [Domain(code="meta"), Domain(code="meta", description="Meta domain", system_prompt="You are a meta assistant.")],
        ],
    )
    def test_membership_sibling_defers_to_root(self, domains: list[Domain], caplog: pytest.LogCaptureFixture):
        """A membership-only sibling Domain (no description/system_prompt) defers to the root's header, silently, in either order."""
        library = DomainLibrary.make_empty()
        with caplog.at_level(logging.WARNING):
            library.add_domains(domains=domains)
        merged = library.get_required_domain("meta")
        assert merged.description == "Meta domain"
        assert merged.system_prompt == "You are a meta assistant."
        assert not [record for record in caplog.records if "declared with different" in record.message]

    def test_same_values_no_warning(self, caplog: pytest.LogCaptureFixture):
        """Two Domains declaring the same non-empty description/system_prompt merge without warning."""
        library = DomainLibrary.make_empty()
        with caplog.at_level(logging.WARNING):
            library.add_domains(
                domains=[
                    Domain(code="meta", description="Meta domain", system_prompt="You are a meta assistant."),
                    Domain(code="meta", description="Meta domain", system_prompt="You are a meta assistant."),
                ]
            )
        merged = library.get_required_domain("meta")
        assert merged.description == "Meta domain"
        assert merged.system_prompt == "You are a meta assistant."
        assert not [record for record in caplog.records if "declared with different" in record.message]

    def test_conflict_keeps_first_and_warns(self, caplog: pytest.LogCaptureFixture):
        """Two Domains declaring different non-empty values keep the first and warn for each field."""
        library = DomainLibrary.make_empty()
        with caplog.at_level(logging.WARNING):
            library.add_domains(
                domains=[
                    Domain(code="meta", description="Meta domain", system_prompt="You are a meta assistant."),
                    Domain(code="meta", description="A different meta domain", system_prompt="You are a different meta assistant."),
                ]
            )
        merged = library.get_required_domain("meta")
        assert merged.description == "Meta domain"
        assert merged.system_prompt == "You are a meta assistant."
        messages = [record.message for record in caplog.records]
        assert any(
            "Domain 'meta' declared with different descriptions: 'Meta domain' vs 'A different meta domain'. Keeping the first." in message
            for message in messages
        )
        assert any("Domain 'meta' declared with different system_prompts. Keeping the first." in message for message in messages)
