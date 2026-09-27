from typing import Any

from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.interpreter_hub import get_concept_library
from tests.unit.pipelex.core.memory.input_shaper.data import build_input_specs


class TestInputShaperJSONEnvelopes:
    def test_json_envelope_carries_the_content_form(self) -> None:
        input_specs = build_input_specs([("payload", "native.JSON", None)])
        provided = {"concept": "native.JSON", "content": {"json_obj": {"a": 1}}}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.JSON"
        assert stuff.content == JSONContent(json_obj={"a": 1})

    def test_json_envelope_around_a_list_of_content_forms_is_r10s_escape(self) -> None:
        """At `JSON[]`, an object keyed `concept` and `content` travels as the `json_obj` of one content form."""
        input_specs = build_input_specs([("payload", "native.JSON", True)])
        envelope_shaped_object = {"concept": "Image", "content": {"url": "photo.jpg"}}
        provided: dict[str, Any] = {"concept": "native.JSON", "content": [{"json_obj": envelope_shaped_object}, {"json_obj": {"b": 2}}]}

        working_memory = InputShaper.shape({"payload": provided}, input_specs=input_specs, concept_provider=get_concept_library())

        stuff = working_memory.root["payload"]
        assert stuff.concept.concept_ref == "native.JSON"
        assert stuff.content == ListContent(items=[JSONContent(json_obj=envelope_shaped_object), JSONContent(json_obj={"b": 2})])
