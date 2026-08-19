"""The stamp writer/parser: round-trip, tamper detection, comment syntax, and options/pipe_ref carry."""

from __future__ import annotations

import pytest

from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.exceptions import CodegenStampError
from pipelex.codegen.stamp import apply_stamp, comment_prefix_for, compute_content_hash, has_stamp, parse_stamped


class TestStamp:
    def _stamp(self, body: str, *, comment_prefix: str, pipe_ref: str | None = None, options: dict[str, str] | None = None) -> str:
        return apply_stamp(
            body,
            crate_fingerprint="fp-123",
            engine_version="0.42.0",
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_PYDANTIC,
            pipe_ref=pipe_ref,
            options=options or {},
            comment_prefix=comment_prefix,
        )

    def test_round_trip_preserves_body_and_fields(self) -> None:
        body = "# header\nfrom __future__ import annotations\n\nclass Foo:\n    pass\n"
        stamped = self._stamp(body, comment_prefix="#")
        parsed = parse_stamped(stamped, comment_prefix="#")
        assert parsed is not None
        assert parsed.body == body  # byte-exact body below the stamp
        assert parsed.stamp.crate_fingerprint == "fp-123"
        assert parsed.stamp.engine_version == "0.42.0"
        assert parsed.stamp.kind == CodegenKind.TYPES
        assert parsed.stamp.target == CodegenTarget.PYTHON_PYDANTIC
        assert parsed.stamp.content_hash == compute_content_hash(body)

    def test_content_hash_covers_only_the_body_not_the_stamp(self) -> None:
        body = "// x\nexport type A = number;\n"
        stamped = self._stamp(body, comment_prefix="//")
        parsed = parse_stamped(stamped, comment_prefix="//")
        assert parsed is not None
        # Recomputing over the recovered body reproduces the recorded hash — the self-describing property.
        assert compute_content_hash(parsed.body) == parsed.stamp.content_hash

    def test_tampering_below_the_stamp_breaks_the_recomputed_hash(self) -> None:
        body = "# a\nclass A:\n    pass\n"
        stamped = self._stamp(body, comment_prefix="#")
        tampered = stamped + "x = 1\n"
        parsed = parse_stamped(tampered, comment_prefix="#")
        assert parsed is not None
        assert compute_content_hash(parsed.body) != parsed.stamp.content_hash

    def test_pipe_ref_and_options_survive_the_round_trip(self) -> None:
        stamped = self._stamp("// b\n", comment_prefix="//", pipe_ref="documents.extract", options={"explicit": "true"})
        parsed = parse_stamped(stamped, comment_prefix="//")
        assert parsed is not None
        assert parsed.stamp.pipe_ref == "documents.extract"
        assert parsed.stamp.options == {"explicit": "true"}

    def test_ts_uses_double_slash_comment_prefix(self) -> None:
        stamped = self._stamp("// b\n", comment_prefix="//")
        assert stamped.startswith("// >>> pipelex-codegen-stamp >>>")
        assert has_stamp(stamped, comment_prefix="//")
        assert not has_stamp(stamped, comment_prefix="#")

    def test_unstamped_text_parses_to_none(self) -> None:
        assert parse_stamped("class A: pass\n", comment_prefix="#") is None

    def test_comment_prefix_by_suffix(self) -> None:
        assert comment_prefix_for("models.py") == "#"
        assert comment_prefix_for("types.ts") == "//"

    def test_unstampable_file_type_raises(self) -> None:
        with pytest.raises(CodegenStampError):
            comment_prefix_for("data.json")

    def test_uncommented_line_inside_the_header_is_rejected(self) -> None:
        # An executable line hiding between the markers leaves the body — and its hash — untouched,
        # so only the header gate can catch it.
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#")
        injected = stamped.replace("# options: {}", 'raise RuntimeError("edited")\n# options: {}')
        assert parse_stamped(injected, comment_prefix="#") is None

    def test_blank_line_inside_the_header_is_rejected(self) -> None:
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#")
        injected = stamped.replace("# options: {}", "\n# options: {}")
        assert parse_stamped(injected, comment_prefix="#") is None

    def test_commented_unknown_field_still_parses(self) -> None:
        # Additive tolerance, pinned: a stamp gaining a field stays readable by today's parser, which
        # is why the stamp header carries no version of its own. Over-tightening the gate would break it.
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#")
        extended = stamped.replace("# options: {}", "# future_field: value\n# options: {}")
        parsed = parse_stamped(extended, comment_prefix="#")
        assert parsed is not None
        assert parsed.stamp.crate_fingerprint == "fp-123"

    @pytest.mark.parametrize("options_value", ['{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}', "Infinity"])
    def test_non_standard_json_constants_in_options_are_rejected(self, options_value: str) -> None:
        # Python's `json` accepts these; no conformant JSON parser does. The stamp header is a
        # cross-language interchange format, so a stamp only Python can read is not a valid stamp.
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#")
        tampered = stamped.replace("# options: {}", f"# options: {options_value}")
        assert parse_stamped(tampered, comment_prefix="#") is None

    def test_standard_options_json_still_parses(self) -> None:
        empty = parse_stamped(self._stamp("# a\n", comment_prefix="#"), comment_prefix="#")
        assert empty is not None
        assert empty.stamp.options == {}
        populated = parse_stamped(self._stamp("# a\n", comment_prefix="#", options={"explicit": "true", "flavor": "strict"}), comment_prefix="#")
        assert populated is not None
        assert populated.stamp.options == {"explicit": "true", "flavor": "strict"}
