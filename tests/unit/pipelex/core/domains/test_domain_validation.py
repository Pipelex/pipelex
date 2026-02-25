import pytest

from pipelex.core.domains.validation import is_domain_code_valid


class TestDomainValidation:
    """Test domain code validation including hierarchical dotted paths."""

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            # Single-segment domains
            ("legal", True),
            ("my_app", True),
            ("native", True),
            ("a", True),
            # Hierarchical domains
            ("legal.contracts", True),
            ("legal.contracts.shareholder", True),
            ("a.b.c", True),
            ("my_app.sub_domain", True),
            # Cross-package domain codes
            ("scoring_lib->scoring", True),
            ("my_lib->legal.contracts", True),
            ("alias->a.b.c", True),
            ("lib->native", True),
            # Cross-package with invalid remainder
            ("lib->Legal", False),
            ("lib->", False),
            ("lib->legal.", False),
            ("lib->.legal", False),
            ("lib->legal..contracts", False),
            # Invalid
            ("Legal", False),
            ("legal.", False),
            (".legal", False),
            ("legal..contracts", False),
            ("legal-contracts", False),
            ("", False),
            ("123abc", False),
            ("UPPER", False),
            ("legal.Contracts", False),
            ("legal.contracts.", False),
            (".legal.contracts", False),
            ("legal..contracts.shareholder", False),
        ],
    )
    def test_is_domain_code_valid(self, code: str, expected: bool):
        """Test domain code validation accepts hierarchical dotted paths."""
        assert is_domain_code_valid(code=code) == expected
