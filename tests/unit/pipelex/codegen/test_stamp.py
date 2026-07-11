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
