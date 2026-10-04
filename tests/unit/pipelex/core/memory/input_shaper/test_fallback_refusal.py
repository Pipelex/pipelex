from typing import Any

import pytest

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.core.memory.exceptions import (
    StructureValidationError,
)
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs


class TestInputShaperFallbackRefusal:
    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity"),
        [
            ("native.Dynamic", None),
            ("native.Dynamic", True),
            ("native.Composite", True),
            ("native.Html", True),
            ("native.TextAndImages", True),
            ("native.SearchResult", True),
            ("native.Page", True),
        ],
    )
    def test_a_list_of_objects_is_refused_naming_the_input(self, concept_ref: str, multiplicity: VariableMultiplicity | None) -> None:
        input_specs = build_input_specs([("records", concept_ref, multiplicity)])
        records_input: dict[str, Any] = {"records": [{"a": 1}, {"b": 2}]}

        with pytest.raises(StructureValidationError) as exc_info:
            InputShaper.shape(records_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        error = exc_info.value
        message = str(error)
        assert "Input 'records'" in message
        assert f"'{concept_ref}'" in message
        assert "a list of 2 item(s)" in message
        assert "Expected shape:" in message
        # The factory's own text, with its `typing.Union[...]` spelling of what it accepts, stays on
        # the chain as the cause and out of what a caller reads.
        assert "typing.Union" not in message
        assert isinstance(error.__cause__, StuffFactoryError)
        assert error.error_domain == ErrorDomain.INPUT
        # The fix is on the author's side: the declaration, and no envelope.
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert "'JSON[]'" in error.user_action.detail
        assert "envelope" not in error.user_action.detail

    def test_a_bare_number_at_a_dynamic_slot_is_refused_naming_the_input(self) -> None:
        input_specs = build_input_specs([("payload", "native.Dynamic", None)])
        payload_input: dict[str, Any] = {"payload": 3}

        with pytest.raises(StructureValidationError, match=r"Input 'payload' could not be built as 'native\.Dynamic'") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        assert "a number (3)" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, StuffFactoryError)

    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity", "provided_value", "suggested_declaration"),
        [
            ("native.Dynamic", None, 3, "'Anything'"),
            ("native.Dynamic", None, True, "'Anything'"),
            ("native.Dynamic", True, [1, "a"], "'Anything[]'"),
            ("native.Dynamic", True, [{"a": 1}, {"b": 2}], "'JSON[]'"),
        ],
    )
    def test_the_advice_names_the_declaration_that_reads_the_value(
        self, concept_ref: str, multiplicity: VariableMultiplicity | None, provided_value: Any, suggested_declaration: str
    ) -> None:
        input_specs = build_input_specs([("payload", concept_ref, multiplicity)])
        payload_input: dict[str, Any] = {"payload": provided_value}

        with pytest.raises(StructureValidationError, match="with no reading for this one") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        user_action = exc_info.value.user_action
        assert user_action is not None
        assert f"as {suggested_declaration}," in user_action.detail

    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity", "provided_value", "factory_reason"),
        [
            ("native.Html", True, [], "empty list"),
            ("native.Dynamic", True, [TextContent(text="a"), NumberContent(number=1)], "not of the same type"),
            # `Anything[]` refuses a nested list and a null item too, so no declaration is advised.
            ("native.Dynamic", True, [[1, 2], [3]], "could not be built"),
            ("native.Dynamic", True, [1, None], "could not be built"),
            # NaN, an object holding one, and envelope-shaped items are refused by every declaration too.
            ("native.Dynamic", None, float("nan"), "Unexpected type"),
            ("native.Dynamic", True, [1, float("inf")], "Cannot create Stuff from list"),
            ("native.Dynamic", None, {"a": float("nan")}, "should represent a StuffContentOrData"),
            ("native.Dynamic", True, [{"concept": "Text", "content": "a"}], "Cannot create Stuff from list"),
        ],
    )
    def test_a_refusal_that_is_not_about_a_reading_keeps_the_factory_s_reason(
        self, concept_ref: str, multiplicity: VariableMultiplicity | None, provided_value: Any, factory_reason: str
    ) -> None:
        input_specs = build_input_specs([("payload", concept_ref, multiplicity)])
        payload_input: dict[str, Any] = {"payload": provided_value}

        with pytest.raises(StructureValidationError, match=r"Input 'payload' could not be built as") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        message = str(exc_info.value)
        assert factory_reason in message
        assert "no reading" not in message
        assert isinstance(exc_info.value.__cause__, StuffFactoryError)

    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity", "provided_value"),
        [
            ("native.Choice", None, {"choice": "billing"}),
            ("native.Choice", None, {"choice": "billing", "confidence": 0.9}),
            ("native.Rating", None, {"level": 2}),
            ("native.Html", None, {"inner_html": "<p>hi</p>"}),
            ("native.Html", True, [{"inner_html": "<p>a</p>"}, {"inner_html": "<p>b</p>"}]),
        ],
    )
    def test_the_declared_concept_s_own_content_unwrapped_is_told_to_send_the_envelope(
        self, concept_ref: str, multiplicity: VariableMultiplicity | None, provided_value: Any
    ) -> None:
        input_specs = build_input_specs([("payload", concept_ref, multiplicity)])
        payload_input: dict[str, Any] = {"payload": provided_value}

        with pytest.raises(StructureValidationError, match="without the envelope that names its concept") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        error = exc_info.value
        assert f"could not be built as '{concept_ref}'" in str(error)
        assert "Expected shape:" in str(error)
        assert isinstance(error.__cause__, StuffFactoryError)
        # The value is right in substance: declaring the input as `JSON` would discard the concept the method asked for.
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert "expected shape" in error.user_action.detail
        assert "Declare" not in error.user_action.detail

    @pytest.mark.parametrize(
        ("concept_ref", "multiplicity", "provided_value", "suggested_declaration"),
        [
            # A key the structure does not have, or a field of the wrong kind, is not the concept's content.
            ("native.Choice", None, {"choice": "billing", "team": "support"}, "'JSON'"),
            ("native.Choice", None, {"choice": 3}, "'JSON'"),
            ("native.Html", True, [{"inner_html": "<p>a</p>"}, {"b": 2}], "'JSON[]'"),
            # `Composite` holds any object, so fitting it says nothing about what the caller meant.
            ("native.Composite", True, [{"a": 1}], "'JSON[]'"),
        ],
    )
    def test_an_object_that_is_not_the_declared_concept_s_content_keeps_the_declaration_advice(
        self, concept_ref: str, multiplicity: VariableMultiplicity | None, provided_value: Any, suggested_declaration: str
    ) -> None:
        input_specs = build_input_specs([("payload", concept_ref, multiplicity)])
        payload_input: dict[str, Any] = {"payload": provided_value}

        with pytest.raises(StructureValidationError, match="with no reading for this one") as exc_info:
            InputShaper.shape(payload_input, input_specs=input_specs, concept_provider=get_concept_library(), read_scope=None)

        user_action = exc_info.value.user_action
        assert user_action is not None
        assert f"as {suggested_declaration}," in user_action.detail
