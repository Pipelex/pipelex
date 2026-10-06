from pipelex.codegen.emitters.naming import allocate_ts_type_names, python_class_name, snake_to_pascal, ts_type_name
from pipelex.codegen.resolved_concepts import ResolvedConcept, ResolvedLibrary


def _resolved_concept(*, domain: str, code: str, needs_qualification: bool = False) -> ResolvedConcept:
    return ResolvedConcept(
        concept_ref=f"{domain}.{code}",
        domain=domain,
        code=code,
        description=f"{code} concept",
        is_native=False,
        needs_qualification=needs_qualification,
        base_ref=None,
        fields=[],
        structureless=False,
        imprecision_reason=None,
        opaque_python_class=None,
    )


class TestNaming:
    """Unit tests for the shared name-derivation rules (see the codegen spec)."""

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

    def test_ts_name_allocation_disambiguates_non_injective_domains(self):
        library = ResolvedLibrary(
            mthds_version="0.1.0",
            concepts=[
                _resolved_concept(domain="foo.bar", code="Result", needs_qualification=True),
                _resolved_concept(domain="foo_bar", code="Result", needs_qualification=True),
            ],
        )

        assert allocate_ts_type_names(library) == {
            "foo.bar.Result": "FooBarResult",
            "foo_bar.Result": "FooBarResult2",
        }

    def test_ts_name_allocation_preserves_bare_name_over_qualified_collision(self):
        library = ResolvedLibrary(
            mthds_version="0.1.0",
            concepts=[
                _resolved_concept(domain="alpha", code="Result", needs_qualification=True),
                _resolved_concept(domain="other", code="AlphaResult"),
                _resolved_concept(domain="other", code="AlphaResult2"),
            ],
        )

        assert allocate_ts_type_names(library) == {
            "alpha.Result": "AlphaResult3",
            "other.AlphaResult": "AlphaResult",
            "other.AlphaResult2": "AlphaResult2",
        }

    def test_ts_name_allocation_is_independent_of_input_order(self):
        concepts = [
            _resolved_concept(domain="foo.bar", code="Result", needs_qualification=True),
            _resolved_concept(domain="foo_bar", code="Result", needs_qualification=True),
            _resolved_concept(domain="alpha", code="Result", needs_qualification=True),
            _resolved_concept(domain="other", code="AlphaResult"),
        ]

        forward = ResolvedLibrary(mthds_version="0.1.0", concepts=concepts)
        reversed_library = ResolvedLibrary(mthds_version="0.1.0", concepts=list(reversed(concepts)))

        assert allocate_ts_type_names(forward) == allocate_ts_type_names(reversed_library)

    def test_ts_name_allocation_reserves_derived_schema_symbols(self):
        library = ResolvedLibrary(
            mthds_version="0.1.0",
            concepts=[
                _resolved_concept(domain="demo", code="Foo"),
                _resolved_concept(domain="demo", code="FooSchema"),
            ],
        )

        assert allocate_ts_type_names(library) == {
            "demo.Foo": "Foo",
            "demo.FooSchema": "FooSchema2",
        }
