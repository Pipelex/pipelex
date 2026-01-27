import pytest

from pipelex.cogt.models.model_reference import (
    NAMESPACE_ALIAS,
    NAMESPACE_HANDLE,
    NAMESPACE_PRESET,
    NAMESPACE_WATERFALL,
    SIGIL_ALIAS,
    SIGIL_PRESET,
    SIGIL_WATERFALL,
    ModelReference,
    ModelReferenceKind,
    ModelReferenceParseError,
    parse_model_reference,
)


class TestModelReferenceParse:
    """Tests for ModelReference.parse() method."""

    # --- Sigil prefix parsing ---

    def test_parse_preset_with_sigil(self):
        """Test parsing preset reference with $ sigil."""
        ref = ModelReference.parse("$llm_for_creativity")
        assert ref.kind == ModelReferenceKind.PRESET
        assert ref.name == "llm_for_creativity"
        assert ref.raw == "$llm_for_creativity"

    def test_parse_alias_with_sigil(self):
        """Test parsing alias reference with @ sigil."""
        ref = ModelReference.parse("@best-claude")
        assert ref.kind == ModelReferenceKind.ALIAS
        assert ref.name == "best-claude"
        assert ref.raw == "@best-claude"

    def test_parse_waterfall_with_sigil(self):
        """Test parsing waterfall reference with ~ sigil."""
        ref = ModelReference.parse("~small-llm")
        assert ref.kind == ModelReferenceKind.WATERFALL
        assert ref.name == "small-llm"
        assert ref.raw == "~small-llm"

    # --- Namespace prefix parsing ---

    def test_parse_preset_with_namespace(self):
        """Test parsing preset reference with preset: namespace."""
        ref = ModelReference.parse("preset:llm_for_creativity")
        assert ref.kind == ModelReferenceKind.PRESET
        assert ref.name == "llm_for_creativity"
        assert ref.raw == "preset:llm_for_creativity"

    def test_parse_alias_with_namespace(self):
        """Test parsing alias reference with alias: namespace."""
        ref = ModelReference.parse("alias:best-claude")
        assert ref.kind == ModelReferenceKind.ALIAS
        assert ref.name == "best-claude"
        assert ref.raw == "alias:best-claude"

    def test_parse_waterfall_with_namespace(self):
        """Test parsing waterfall reference with waterfall: namespace."""
        ref = ModelReference.parse("waterfall:small-llm")
        assert ref.kind == ModelReferenceKind.WATERFALL
        assert ref.name == "small-llm"
        assert ref.raw == "waterfall:small-llm"

    def test_parse_handle_with_namespace(self):
        """Test parsing handle reference with handle: namespace."""
        ref = ModelReference.parse("handle:gpt-4o-mini")
        assert ref.kind == ModelReferenceKind.HANDLE
        assert ref.name == "gpt-4o-mini"
        assert ref.raw == "handle:gpt-4o-mini"

    # --- Bare string (defaults to HANDLE) ---

    def test_parse_bare_string_as_handle(self):
        """Test that bare strings are parsed as HANDLE type."""
        ref = ModelReference.parse("gpt-4o-mini")
        assert ref.kind == ModelReferenceKind.HANDLE
        assert ref.name == "gpt-4o-mini"
        assert ref.raw == "gpt-4o-mini"

    def test_parse_bare_string_with_underscores(self):
        """Test bare string with underscores is parsed as HANDLE."""
        ref = ModelReference.parse("claude_3_haiku")
        assert ref.kind == ModelReferenceKind.HANDLE
        assert ref.name == "claude_3_haiku"

    def test_parse_bare_string_with_dots(self):
        """Test bare string with dots is parsed as HANDLE."""
        ref = ModelReference.parse("gpt-4.5-turbo")
        assert ref.kind == ModelReferenceKind.HANDLE
        assert ref.name == "gpt-4.5-turbo"

    # --- Whitespace handling ---

    def test_parse_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        ref = ModelReference.parse("  $llm_preset  ")
        assert ref.kind == ModelReferenceKind.PRESET
        assert ref.name == "llm_preset"

    # --- Sigil/namespace equivalence ---

    @pytest.mark.parametrize(
        ("sigil_input", "namespace_input"),
        [
            ("$my_preset", "preset:my_preset"),
            ("@my_alias", "alias:my_alias"),
            ("~my_waterfall", "waterfall:my_waterfall"),
        ],
    )
    def test_sigil_namespace_equivalence(self, sigil_input: str, namespace_input: str):
        """Test that sigil and namespace prefixes produce equivalent results."""
        sigil_ref = ModelReference.parse(sigil_input)
        namespace_ref = ModelReference.parse(namespace_input)

        assert sigil_ref.kind == namespace_ref.kind
        assert sigil_ref.name == namespace_ref.name

    # --- Error cases ---

    def test_parse_empty_string_raises(self):
        """Test that empty string raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("")
        assert "cannot be empty" in str(exc_info.value)
        assert exc_info.value.raw_value == ""

    def test_parse_whitespace_only_raises(self):
        """Test that whitespace-only string raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("   ")
        assert "cannot be empty" in str(exc_info.value)

    def test_parse_sigil_without_name_raises(self):
        """Test that sigil without name raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("$")
        assert "no name after" in str(exc_info.value)
        assert exc_info.value.raw_value == "$"

    def test_parse_alias_sigil_without_name_raises(self):
        """Test that @ sigil without name raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("@")
        assert "no name after" in str(exc_info.value)

    def test_parse_waterfall_sigil_without_name_raises(self):
        """Test that ~ sigil without name raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("~")
        assert "no name after" in str(exc_info.value)

    def test_parse_namespace_without_name_raises(self):
        """Test that namespace prefix without name raises ModelReferenceParseError."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("preset:")
        assert "no name after" in str(exc_info.value)

    def test_error_includes_syntax_help(self):
        """Test that parse errors include syntax help."""
        with pytest.raises(ModelReferenceParseError) as exc_info:
            ModelReference.parse("")
        error_message = str(exc_info.value)
        assert "Model reference syntax" in error_message
        assert "$preset_name" in error_message
        assert "@alias_name" in error_message
        assert "~waterfall_name" in error_message


class TestModelReferenceHelpers:
    """Tests for ModelReference helper methods."""

    def test_is_preset(self):
        """Test is_preset() method."""
        preset_ref = ModelReference.parse("$my_preset")
        handle_ref = ModelReference.parse("gpt-4o-mini")

        assert preset_ref.is_preset() is True
        assert handle_ref.is_preset() is False

    def test_is_alias(self):
        """Test is_alias() method."""
        alias_ref = ModelReference.parse("@my_alias")
        handle_ref = ModelReference.parse("gpt-4o-mini")

        assert alias_ref.is_alias() is True
        assert handle_ref.is_alias() is False

    def test_is_waterfall(self):
        """Test is_waterfall() method."""
        waterfall_ref = ModelReference.parse("~my_waterfall")
        handle_ref = ModelReference.parse("gpt-4o-mini")

        assert waterfall_ref.is_waterfall() is True
        assert handle_ref.is_waterfall() is False

    def test_is_handle(self):
        """Test is_handle() method."""
        handle_ref = ModelReference.parse("gpt-4o-mini")
        preset_ref = ModelReference.parse("$my_preset")

        assert handle_ref.is_handle() is True
        assert preset_ref.is_handle() is False


class TestParseModelReference:
    """Tests for parse_model_reference() BeforeValidator function."""

    def test_parse_string(self):
        """Test parsing a string value."""
        ref = parse_model_reference("$my_preset")
        assert ref.kind == ModelReferenceKind.PRESET
        assert ref.name == "my_preset"

    def test_parse_model_reference_passthrough(self):
        """Test that existing ModelReference is passed through."""
        original = ModelReference(
            kind=ModelReferenceKind.PRESET,
            name="my_preset",
            raw="$my_preset",
        )
        result = parse_model_reference(original)
        assert result is original

    def test_parse_non_string_passthrough(self):
        """Test that non-string/non-ModelReference types pass through unchanged.

        This allows dicts to be handled by other union members (e.g., LLMSetting).
        """
        dict_value = {"model": "gpt-4o-mini", "temperature": 0.5}
        result = parse_model_reference(dict_value)
        assert result is dict_value  # Should be the exact same object

        int_value = 123
        result = parse_model_reference(int_value)
        assert result is int_value


class TestModelReferenceHashability:
    """Tests for ModelReference hashability (frozen=True)."""

    def test_model_reference_is_hashable(self):
        """Test that ModelReference can be used in sets and as dict keys."""
        ref1 = ModelReference.parse("$my_preset")
        ref2 = ModelReference.parse("@my_alias")

        # Should not raise
        model_set = {ref1, ref2}
        assert len(model_set) == 2

        model_dict = {ref1: "value1", ref2: "value2"}
        assert model_dict[ref1] == "value1"

    def test_same_references_have_same_hash(self):
        """Test that equivalent references have the same hash."""
        ref1 = ModelReference.parse("$my_preset")
        ref2 = ModelReference.parse("$my_preset")

        assert hash(ref1) == hash(ref2)
        assert ref1 == ref2


class TestConstants:
    """Tests for module constants."""

    def test_sigil_constants(self):
        """Test sigil prefix constants."""
        assert SIGIL_PRESET == "$"
        assert SIGIL_ALIAS == "@"
        assert SIGIL_WATERFALL == "~"

    def test_namespace_constants(self):
        """Test namespace prefix constants."""
        assert NAMESPACE_PRESET == "preset:"
        assert NAMESPACE_ALIAS == "alias:"
        assert NAMESPACE_WATERFALL == "waterfall:"
        assert NAMESPACE_HANDLE == "handle:"
