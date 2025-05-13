# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC
from typing import Annotated, Any, Dict, List, Literal, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex import log, pretty_print

# This tests a solution which is not ideal, but it works.
# We found a better way to handle BaseModel subclasses so, in the end, we don't use this solution.
# We're keeping the test until we're sure we don't need it anymore.


class Step(BaseModel, ABC):
    """Base class for a step in the process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @override
    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "Step":
        """
        Override model_validate to create the correct subclass based on class_name
        """
        if not isinstance(obj, dict):
            raise TypeError("Expected a dictionary of values")
        obj_dict: Dict[str, Any] = obj
        class_name = obj_dict.get("step_type", None)
        if not class_name:
            log.debug(f"No class_name found in object, using default class: {cls}")
            return super().model_validate(obj, **kwargs)
        log.debug(f"Found class_name: {class_name}")
        target_class = cls.get_class_by_name(class_name)
        log.debug(f"Target class: {target_class}")
        # return target_class.model_validate(obj_dict)
        return target_class(**obj_dict)

    @classmethod
    def get_class_by_name(cls, class_name: str) -> Type["Step"]:
        """
        Get the appropriate class based on the class_name.
        Should be implemented by the root class of the hierarchy.
        """
        the_class = CLASS_MAPPING.get(class_name)
        if not the_class:
            raise ValueError(f"Unknown class_name: {class_name}")
        return the_class


class NodeStep(Step):
    """Represents a node in the process."""

    step_type: Literal["NodeStep"] = "NodeStep"

    concept_code: str
    path_modifier: Optional[int] = None


StepUnion = Annotated[
    Union[NodeStep, "JunctionStep"],
    Field(discriminator="step_type"),
]


class Choice(BaseModel):
    """Represents a choice within a junction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: str
    steps: List[StepUnion]


class JunctionStep(Step):
    """Represents a junction with multiple choices."""

    step_type: Literal["JunctionStep"] = "JunctionStep"
    expression: str
    choices: List[Choice]


class TestSerDeUnionDiscriminator:
    def test_serde_primitives(self):
        example_node_step = NodeStep(concept_code="123")
        dump = example_node_step.model_dump()
        assert dump == {
            "step_type": "NodeStep",
            "concept_code": "123",
            "path_modifier": None,
        }

        recreated = NodeStep.model_validate(dump)
        assert recreated == example_node_step

    def test_serde_with_list_in_typed_model(self):
        example_junction_step = JunctionStep(expression="123", choices=[Choice(value="456", steps=[NodeStep(concept_code="789")])])
        dump_junction = example_junction_step.model_dump()
        assert dump_junction == {
            "step_type": "JunctionStep",
            "expression": "123",
            "choices": [
                {
                    "value": "456",
                    "steps": [
                        {
                            "step_type": "NodeStep",
                            "concept_code": "789",
                            "path_modifier": None,
                        }
                    ],
                }
            ],
        }
        pretty_print(dump_junction, title="dump_junction OK:")

        recreated_junction = JunctionStep.model_validate(dump_junction)
        pretty_print(example_junction_step, title="example_junction_step:")
        pretty_print(recreated_junction, title="recreated_junction:")
        assert recreated_junction == example_junction_step

    def test_serde_with_list_in_other_model(self):
        example_choice = Choice(value="123", steps=[NodeStep(concept_code="456")])
        dump = example_choice.model_dump()
        assert dump == {
            "value": "123",
            "steps": [
                {
                    "step_type": "NodeStep",
                    "concept_code": "456",
                    "path_modifier": None,
                }
            ],
        }

        recreated_choice = Choice.model_validate(dump)
        assert recreated_choice == example_choice

    def test_serde_list_subclasses(self):
        example_list: List[Step] = [
            NodeStep(concept_code="123"),
            JunctionStep(expression="456", choices=[Choice(value="789", steps=[NodeStep(concept_code="101112")])]),
        ]
        pretty_print(example_list, title="example_list:")
        example_list_dump = [step.model_dump() for step in example_list]
        pretty_print(example_list_dump, title="example_list_dump:")
        assert example_list_dump == [
            {
                "step_type": "NodeStep",
                "concept_code": "123",
                "path_modifier": None,
            },
            {
                "step_type": "JunctionStep",
                "expression": "456",
                "choices": [
                    {
                        "value": "789",
                        "steps": [
                            {
                                "step_type": "NodeStep",
                                "concept_code": "101112",
                                "path_modifier": None,
                            }
                        ],
                    }
                ],
            },
        ]

        recreated_list = [Step.model_validate(dump) for dump in example_list_dump]
        assert recreated_list == example_list


# Map of class names to classes for secure deserialization
CLASS_MAPPING: Dict[str, Type[Step]] = {
    "NodeStep": NodeStep,
    "JunctionStep": JunctionStep,
}
