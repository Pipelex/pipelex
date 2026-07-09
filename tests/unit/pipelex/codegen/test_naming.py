from pipelex.codegen.emitters.naming import python_class_name, snake_to_camel, snake_to_pascal, ts_type_name


class TestNaming:
    """Unit tests for the shared name-derivation rules (see docs/specs/pipelex-codegen.md)."""

    def test_snake_to_camel(self):
        assert snake_to_camel("value") == "value"
        assert snake_to_camel("item_count") == "itemCount"
        assert snake_to_camel("run_the_pipeline") == "runThePipeline"

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
