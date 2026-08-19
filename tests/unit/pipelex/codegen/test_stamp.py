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

    @pytest.mark.parametrize("line_boundary", ["\u2028", "\u2029", "\u0085"])
    def test_a_field_value_carrying_a_unicode_line_boundary_still_round_trips(self, line_boundary: str) -> None:
        r"""What the emitter writes, the parser must read back — the header gate splits on `\n` and nothing else.

        `str.splitlines` also breaks on U+2028, U+2029 and U+0085, and `apply_stamp` passes all three through
        verbatim (`pipe_ref` is not encoded at all, and `json.dumps` leaves them unescaped under
        `ensure_ascii=False`). Splitting on them would make the gate reject a header the emitter had just
        written, so `codegen check` would report a freshly generated file as hand-edited for good — no
        regeneration could clear it, because regeneration writes the same bytes again.
        """
        pipe_ref = f"my_domain.my{line_boundary}pipe"
        options = {"note": f"a{line_boundary}b"}
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#", pipe_ref=pipe_ref, options=options)

        parsed = parse_stamped(stamped, comment_prefix="#")

        assert parsed is not None
        # Not merely accepted — the value survives whole. A `splitlines` field parser would truncate it here.
        assert parsed.stamp.pipe_ref == pipe_ref
        assert parsed.stamp.options == options

    def test_commented_unknown_field_still_parses(self) -> None:
        # Additive tolerance, pinned: a stamp gaining a field stays readable by today's parser, which
        # is why the stamp header carries no version of its own. Over-tightening the gate would break it.
        stamped = self._stamp("# a\nclass A:\n    pass\n", comment_prefix="#")
        extended = stamped.replace("# options: {}", "# future_field: value\n# options: {}")
        parsed = parse_stamped(extended, comment_prefix="#")
        assert parsed is not None
        assert parsed.stamp.crate_fingerprint == "fp-123"

    # A bare top-level constant is deliberately not in this list: `_parse_options` already rejects any
    # non-object payload, so that case stays green with the `parse_constant` guard removed and would
    # pin nothing. Every case here must be one the guard alone catches.
    @pytest.mark.parametrize("options_value", ['{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}', '{"a": 1, "b": NaN}'])
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
