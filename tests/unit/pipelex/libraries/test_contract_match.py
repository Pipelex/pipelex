import pytest

from pipelex.libraries.contract_match import contracts_match
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint


class ConcretePipeBlueprint(PipeBlueprint):
    pass


def _make_blueprint(*, inputs: dict[str, str] | None = None, output: str = "Text") -> ConcretePipeBlueprint:
    return ConcretePipeBlueprint(
        type="PipeLLM",
        pipe_category="PipeOperator",
        description="contract match test pipe",
        inputs=inputs,
        output=output,
    )


class TestContractsMatchPresenceMarkers:
    """Contract canonicalization compares presence markers (D5) on top of concept identity + multiplicity."""

    def test_equivalent_spellings_with_same_marker_match(self):
        existing = _make_blueprint(inputs={"brief": "Brief?"}, output="native.Text?")
        incoming = _make_blueprint(inputs={"brief": "thisdomain.Brief?"}, output="Text?")
        assert contracts_match(existing=existing, incoming=incoming, domain_code="thisdomain")

    @pytest.mark.parametrize(
        ("existing_spec", "incoming_spec"),
        [
            ("Brief", "Brief?"),
            ("Brief?", "Brief"),
            ("Brief!", "Brief?"),
            ("Brief!", "Brief"),
        ],
    )
    def test_differing_input_markers_do_not_match(self, existing_spec: str, incoming_spec: str):
        existing = _make_blueprint(inputs={"brief": existing_spec})
        incoming = _make_blueprint(inputs={"brief": incoming_spec})
        assert not contracts_match(existing=existing, incoming=incoming, domain_code="thisdomain")

    def test_differing_output_markers_do_not_match(self):
        existing = _make_blueprint(output="Brief?")
        incoming = _make_blueprint(output="Brief")
        assert not contracts_match(existing=existing, incoming=incoming, domain_code="thisdomain")

    def test_multiplicity_suffixes_stay_distinct(self):
        """Pre-existing behavior: [] and [1] compare as text, never conflated."""
        existing = _make_blueprint(output="Brief[]")
        incoming = _make_blueprint(output="Brief[1]")
        assert not contracts_match(existing=existing, incoming=incoming, domain_code="thisdomain")
