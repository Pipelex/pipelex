from typing import Any

import pytest
from kajson import kajson
from kajson.exceptions import KajsonDecoderError
from pydantic import BaseModel


class _Envelope(BaseModel):
    """Mimics a PipeOutput-shaped payload: a BaseModel carrying a plain-dict field.

    The dehydrated working_memory_raw is exactly this shape: nested dicts that
    travel through kajson.dumps / kajson.loads at the Temporal data-converter
    boundary. The envelope itself is a BaseModel (so kajson encodes/decodes it),
    but the payload field is a free-form dict whose nested keys are pipelex's
    responsibility — kajson must leave it alone.
    """

    payload: dict[str, Any]


class TestKajsonMarkerIsolation:
    """Wire-format contract tests: kajson's universal decoder gates on __class__.

    Pipelex's deferred-binding wire format uses __pipelex_class__/__pipelex_module__
    deliberately so kajson's decoder ignores it. These tests pin that contract:
    if anyone ever re-collides the namespace, both tests catch it.
    """

    def test_pipelex_markers_pass_through_unchanged(self) -> None:
        """Nested dicts with __pipelex_class__ / __pipelex_module__ must round-trip untouched.

        The class name points at a name that is NOT registered anywhere — if kajson
        were to attempt resolution, it would raise. The fact that round-trip succeeds
        proves kajson does not touch the pipelex namespace.
        """
        envelope = _Envelope(
            payload={
                "items": [
                    {
                        "text": "hello",
                        "__pipelex_class__": "DefinitelyNotRegistered__xyz",
                        "__pipelex_module__": "builtins",
                    }
                ]
            }
        )

        encoded = kajson.dumps(envelope)
        decoded = kajson.loads(encoded)

        assert isinstance(decoded, _Envelope)
        assert decoded.payload == envelope.payload

    def test_kajson_markers_raise_for_unknown_class(self) -> None:
        """Inverse oracle: __class__ / __module__ for an unknown class MUST raise.

        This is the original failure mode that triggered the rename. We keep this
        test as a sanity check that kajson's decoder is still strict on its own
        namespace — so any accidental re-collision shows up immediately.
        """
        envelope = _Envelope(
            payload={
                "items": [
                    {
                        "text": "hello",
                        "__class__": "DefinitelyNotRegistered__xyz",
                        "__module__": "builtins",
                    }
                ]
            }
        )

        encoded = kajson.dumps(envelope)

        with pytest.raises(KajsonDecoderError):
            kajson.loads(encoded)
