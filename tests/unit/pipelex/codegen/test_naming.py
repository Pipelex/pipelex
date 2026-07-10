from pipelex.codegen.emitters.naming import python_class_name, runtime_to_emitted_class_names, snake_to_pascal, ts_type_name
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary


def _resolved_concept(
    *,
    domain: str,
    code: str,
    is_native: bool = False,
    needs_qualification: bool = False,
    opaque_python_class: str | None = None,
) -> ResolvedConcept:
    return ResolvedConcept(
        concept_ref=f"{domain}.{code}",
        domain=domain,
        code=code,
        description=f"{code} concept",
        is_native=is_native,
        needs_qualification=needs_qualification,
        base_ref=None,
        fields=[],
        structureless=opaque_python_class is not None,
        imprecision_reason=None,
        opaque_python_class=opaque_python_class,
    )


class TestNaming:
    """Unit tests for the shared name-derivation rules (see docs/specs/pipelex-codegen.md)."""

    def test_snake_to_pascal(self):
        assert snake_to_pascal("value") == "Value"
        assert snake_to_pascal("legal_contracts") == "LegalContracts"

    def test_python_class_name_bare_when_unique(self):
        assert python_class_name(domain="pipeline", code="Report", needs_qualification=False) == "Report"

    def test_python_class_name_qualified_on_collision(self):
        # The runtime seed uses a double underscore, with dotted domains interpuncted (U+00B7).
        assert python_class_name(domain="alpha", code="Result", needs_qualification=True) == "alpha__Result"
        assert python_class_name(domain="legal.contracts", code="Result", needs_qualification=True) == "legal·contracts__Result"

    def test_ts_type_name_bare_when_unique(self):
        assert ts_type_name(domain="pipeline", code="Report", needs_qualification=False) == "Report"

    def test_ts_type_name_qualified_on_collision(self):
        # TS cannot use the interpunct; a colliding type PascalCases and joins the domain segments.
        assert ts_type_name(domain="alpha", code="Result", needs_qualification=True) == "AlphaResult"
        assert ts_type_name(domain="legal.contracts", code="Result", needs_qualification=True) == "LegalContractsResult"

    def test_runtime_to_emitted_class_names(self):
        """Runtime-qualified spellings map to the emitted names; natives and opaque classes are skipped."""
        library = ResolvedLibrary(
            mthds_version="0.1.0",
            concepts=[
                _resolved_concept(domain="pipeline", code="Report"),
                _resolved_concept(domain="alpha", code="Result", needs_qualification=True),
                _resolved_concept(domain="native", code="Text", is_native=True),
                _resolved_concept(domain="pipeline", code="Wrapped", opaque_python_class="UserClass"),
            ],
        )

        mapping = runtime_to_emitted_class_names(library)

        # Unique code: runtime-qualified -> bare; collision: identity; native + opaque: absent.
        assert mapping == {
            "pipeline__Report": "Report",
            "alpha__Result": "alpha__Result",
        }
