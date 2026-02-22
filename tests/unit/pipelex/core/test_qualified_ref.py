import pytest
from pydantic import ValidationError

from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError


class TestQualifiedRef:
    """Test centralized reference parsing via QualifiedRef."""

    # ========== parse() ==========

    @pytest.mark.parametrize(
        ("raw", "expected_domain", "expected_code"),
        [
            ("Text", None, "Text"),
            ("compute_score", None, "compute_score"),
            ("native.Text", "native", "Text"),
            ("scoring.compute_score", "scoring", "compute_score"),
            ("legal.contracts.NonCompeteClause", "legal.contracts", "NonCompeteClause"),
            ("a.b.c.D", "a.b.c", "D"),
        ],
    )
    def test_parse_valid(self, raw: str, expected_domain: str | None, expected_code: str):
        """Test parse splits correctly on last dot."""
        ref = QualifiedRef.parse(raw)
        assert ref.domain_path == expected_domain
        assert ref.local_code == expected_code

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            ".extract",
            "domain.",
            "legal..contracts.X",
            "..foo",
            "foo..",
        ],
    )
    def test_parse_invalid(self, raw: str):
        """Test parse raises on invalid input."""
        with pytest.raises(QualifiedRefError):
            QualifiedRef.parse(raw)

    # ========== parse_concept_ref() ==========

    @pytest.mark.parametrize(
        ("raw", "expected_domain", "expected_code"),
        [
            ("native.Text", "native", "Text"),
            ("legal.contracts.NonCompeteClause", "legal.contracts", "NonCompeteClause"),
            ("legal.contracts.shareholder.Agreement", "legal.contracts.shareholder", "Agreement"),
            ("myapp.BaseEntity", "myapp", "BaseEntity"),
            ("a.b.c.D", "a.b.c", "D"),
        ],
    )
    def test_parse_concept_ref_valid(self, raw: str, expected_domain: str | None, expected_code: str):
        """Test parse_concept_ref accepts valid concept references."""
        ref = QualifiedRef.parse_concept_ref(raw)
        assert ref.domain_path == expected_domain
        assert ref.local_code == expected_code

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "legal..contracts.X",
            ".Text",
            "native.text",
            "NATIVE.Text",
            "my-app.Entity",
        ],
    )
    def test_parse_concept_ref_invalid(self, raw: str):
        """Test parse_concept_ref raises on invalid input."""
        with pytest.raises(QualifiedRefError):
            QualifiedRef.parse_concept_ref(raw)

    # ========== parse_pipe_ref() ==========

    @pytest.mark.parametrize(
        ("raw", "expected_domain", "expected_code"),
        [
            ("scoring.compute_score", "scoring", "compute_score"),
            ("legal.contracts.extract_clause", "legal.contracts", "extract_clause"),
            ("a.b.c.do_thing", "a.b.c", "do_thing"),
        ],
    )
    def test_parse_pipe_ref_valid(self, raw: str, expected_domain: str | None, expected_code: str):
        """Test parse_pipe_ref accepts valid pipe references."""
        ref = QualifiedRef.parse_pipe_ref(raw)
        assert ref.domain_path == expected_domain
        assert ref.local_code == expected_code

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            ".extract",
            "legal..contracts.x",
            "scoring.ComputeScore",
            "MY_APP.extract",
        ],
    )
    def test_parse_pipe_ref_invalid(self, raw: str):
        """Test parse_pipe_ref raises on invalid input."""
        with pytest.raises(QualifiedRefError):
            QualifiedRef.parse_pipe_ref(raw)

    # ========== full_ref ==========

    def test_full_ref_bare(self):
        """Test full_ref for bare references."""
        ref = QualifiedRef(domain_path=None, local_code="Text")
        assert ref.full_ref == "Text"

    def test_full_ref_qualified(self):
        """Test full_ref for domain-qualified references."""
        ref = QualifiedRef(domain_path="legal.contracts", local_code="NonCompeteClause")
        assert ref.full_ref == "legal.contracts.NonCompeteClause"

    # ========== is_qualified ==========

    def test_is_qualified_true(self):
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        assert ref.is_qualified is True

    def test_is_qualified_false(self):
        ref = QualifiedRef(domain_path=None, local_code="compute_score")
        assert ref.is_qualified is False

    # ========== from_domain_and_code() ==========

    def test_from_domain_and_code(self):
        ref = QualifiedRef.from_domain_and_code(domain_path="legal.contracts", local_code="NonCompeteClause")
        assert ref.domain_path == "legal.contracts"
        assert ref.local_code == "NonCompeteClause"
        assert ref.full_ref == "legal.contracts.NonCompeteClause"

    # ========== is_local_to() / is_external_to() ==========

    def test_is_local_to_same_domain(self):
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        assert ref.is_local_to("scoring") is True

    def test_is_local_to_bare_ref(self):
        """Bare refs are always local."""
        ref = QualifiedRef(domain_path=None, local_code="compute_score")
        assert ref.is_local_to("scoring") is True

    def test_is_local_to_different_domain(self):
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        assert ref.is_local_to("orchestration") is False

    def test_is_external_to_different_domain(self):
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        assert ref.is_external_to("orchestration") is True

    def test_is_external_to_same_domain(self):
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        assert ref.is_external_to("scoring") is False

    def test_is_external_to_bare_ref(self):
        """Bare refs are never external."""
        ref = QualifiedRef(domain_path=None, local_code="compute_score")
        assert ref.is_external_to("scoring") is False

    # ========== Frozen model ==========

    def test_frozen_model(self):
        """Test that QualifiedRef instances are immutable."""
        ref = QualifiedRef(domain_path="scoring", local_code="compute_score")
        with pytest.raises(ValidationError, match="frozen"):
            ref.local_code = "other"  # type: ignore[misc]
