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
