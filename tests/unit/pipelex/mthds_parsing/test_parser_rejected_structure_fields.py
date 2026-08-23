"""Full-bundle parsing of the rejected structure-field probes: the E3 required+default pair and
E7 unknown field-table keys must fail the `.mthds` parse itself with an error naming the offending
keys — not just the pydantic model layer, which the blueprint unit tests already pin.
"""

from pathlib import Path

import pytest

from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser

_REJECTED_DIR = Path(__file__).parents[3] / "data" / "input_semantics" / "rejected"


class TestRejectedStructureFieldParsing:
    def test_required_with_default_fails_the_parse_naming_the_pair(self):
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_REJECTED_DIR / "required_with_default.mthds_invalid")
        message = str(exc_info.value)
        assert "required" in message
        assert "default_value" in message

    def test_unknown_structure_field_key_fails_the_parse_naming_the_key(self):
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(bundle_path=_REJECTED_DIR / "unknown_structure_field_key.mthds_invalid")
        message = str(exc_info.value)
        assert "minimum" in message
