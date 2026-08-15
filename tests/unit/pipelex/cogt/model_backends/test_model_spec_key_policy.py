"""An unknown per-model key is a request header only if it is shaped like one.

`InferenceBackendLibrary.load` used to move every per-model key the blueprint did not know into
`extra_headers`, and every provider factory forwards that dict to the wire. A typo (`max_tokns`) or
a field deleted from the blueprint therefore became an outbound header, silently, while the real
setting went unset. The classifier below is the pure half of the fix: it splits a raw model table
into blueprint fields, headers, and rejected keys, and leaves the policy — fatal or pruned — to the
loader, which is the only party that knows where the table came from.
"""

import pytest

from pipelex.cogt.model_backends.model_spec_keys import ModelSpecKeyRejection, describe_rejected_keys, split_model_spec_keys


class TestSplitModelSpecKeys:
    def test_a_known_blueprint_field_is_never_diverted(self) -> None:
        split = split_model_spec_keys(model_spec_dict={"model_id": "gpt-4o", "max_tokens": 4096, "sdk": "openai"})

        assert split.fields == {"model_id": "gpt-4o", "max_tokens": 4096, "sdk": "openai"}
        assert split.headers == {}
        assert split.rejected == []

    @pytest.mark.parametrize("header_key", ["x-portkey-provider", "x-portkey-config", "anthropic-beta", "api-version"])
    def test_a_header_shaped_key_is_accepted_as_a_header(self, header_key: str) -> None:
        split = split_model_spec_keys(model_spec_dict={"model_id": "gpt-4o", header_key: "value"})

        assert split.fields == {"model_id": "gpt-4o"}
        assert split.headers == {header_key: "value"}
        assert split.rejected == []

    @pytest.mark.parametrize("unknown_key", ["max_tokns", "a_field_we_removed", "endpoint", "foobar"])
    def test_an_unknown_key_without_a_hyphen_is_rejected(self, unknown_key: str) -> None:
        """A blueprint field name is a Python identifier — it never carries a hyphen — so an unknown
        hyphen-less key is a typo or a dead field, never a header the author meant to send.
        """
        split = split_model_spec_keys(model_spec_dict={"model_id": "gpt-4o", unknown_key: "value"})

        assert split.fields == {"model_id": "gpt-4o"}
        assert split.headers == {}
        assert [rejected.key for rejected in split.rejected] == [unknown_key]
        assert split.rejected[0].reason == ModelSpecKeyRejection.NOT_HEADER_SHAPED

    @pytest.mark.parametrize(
        ("near_miss", "known_field"), [("max-tokens", "max_tokens"), ("model-id", "model_id"), ("thinking-mode", "thinking_mode")]
    )
    def test_a_hyphenated_spelling_of_a_known_field_is_rejected_despite_its_shape(self, near_miss: str, known_field: str) -> None:
        """The one hole the shape rule leaves: `max-tokens = 4096` is header-shaped and would go out
        on the wire while the real cap stays unset.
        """
        split = split_model_spec_keys(model_spec_dict={"model_id": "gpt-4o", near_miss: 4096})

        assert split.headers == {}
        assert [rejected.key for rejected in split.rejected] == [near_miss]
        assert split.rejected[0].reason == ModelSpecKeyRejection.HYPHENATED_KNOWN_FIELD
        assert split.rejected[0].near_miss_of == known_field

    @pytest.mark.parametrize("value", [3, True, 1.5, ["a"], {"k": "v"}], ids=["int", "bool", "float", "list", "dict"])
    def test_a_header_shaped_key_with_a_non_string_value_is_rejected(self, value: object) -> None:
        """A request header value is a string. `x-foo = 3` is an unquoted-value mistake, not a header
        to stringify: `str(True)` or `str(["a"])` on the wire is exactly the rogue header this guards against.
        """
        split = split_model_spec_keys(model_spec_dict={"model_id": "gpt-4o", "x-foo": value})

        assert split.fields == {"model_id": "gpt-4o"}
        assert split.headers == {}
        assert [rejected.key for rejected in split.rejected] == ["x-foo"]
        assert split.rejected[0].reason == ModelSpecKeyRejection.NON_STRING_VALUE

    def test_rejected_keys_explain_themselves_and_state_the_rule_once(self) -> None:
        split = split_model_spec_keys(model_spec_dict={"max_tokns": 4096, "max-tokens": 4096})

        description = describe_rejected_keys(rejected=split.rejected)

        assert "'max_tokns' is not a known model-spec field" in description
        assert "'max-tokens' looks like the model-spec field 'max_tokens'" in description
        assert description.count("must contain a hyphen") == 1

    def test_a_near_miss_alone_is_explained_without_the_hyphen_rule(self) -> None:
        """`max-tokens` already contains a hyphen and its own message already names the field to use;
        telling the author the key "must contain a hyphen" would contradict both.
        """
        split = split_model_spec_keys(model_spec_dict={"max-tokens": 4096})

        description = describe_rejected_keys(rejected=split.rejected)

        assert "'max-tokens' looks like the model-spec field 'max_tokens'" in description
        assert "must contain a hyphen" not in description

    def test_a_non_string_value_is_explained_without_the_hyphen_rule(self) -> None:
        """The key does contain a hyphen; telling the author to add one would be wrong advice."""
        split = split_model_spec_keys(model_spec_dict={"x-foo": 3})

        description = describe_rejected_keys(rejected=split.rejected)

        assert "'x-foo' is header-shaped, but its value is not a string" in description
        assert "must be a quoted string" in description
        assert "must contain a hyphen" not in description

    def test_a_shape_rejection_beside_a_value_rejection_still_states_the_hyphen_rule_once(self) -> None:
        split = split_model_spec_keys(model_spec_dict={"max_tokns": 4096, "x-foo": 3})

        description = describe_rejected_keys(rejected=split.rejected)

        assert "'max_tokns' is not a known model-spec field" in description
        assert "'x-foo' is header-shaped, but its value is not a string" in description
        assert description.count("must contain a hyphen") == 1

    def test_the_input_table_is_left_untouched(self) -> None:
        model_spec_dict = {"model_id": "gpt-4o", "x-portkey-provider": "openai", "max_tokns": 4096}
        before = dict(model_spec_dict)

        split_model_spec_keys(model_spec_dict=model_spec_dict)

        assert model_spec_dict == before

    def test_the_rejected_list_keeps_table_order(self) -> None:
        split = split_model_spec_keys(model_spec_dict={"zzz_first": 1, "model_id": "gpt-4o", "aaa_second": 2})

        assert [rejected.key for rejected in split.rejected] == ["zzz_first", "aaa_second"]
