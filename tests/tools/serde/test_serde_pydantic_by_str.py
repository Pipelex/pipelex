# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict

import pytest
from kajson import kajson

from pipelex import pretty_print
from pipelex.core.stuff_content import ImageContent
from pipelex.core.stuff_factory import StuffFactory
from tests.pipelex.asynch.test_client import Example
from tests.pipelex.test_data import PipeTestCases


class TestSerDePydanticByDict:
    @pytest.fixture
    def test_example(self) -> Example:
        """
        Fixture providing a test Example instance with a GanttChart image.

        Returns:
            Example: A test example for serialization testing
        """
        return Example(
            pipe_code="extract_gantt_by_steps",
            output_concept="",
            memory=[
                StuffFactory.make_stuff(
                    concept_code="gantt.GanttChartImage",
                    name="gantt_chart_image",
                    content=ImageContent(url=PipeTestCases.URL_IMG_GANTT_1),
                ),
            ],
        )

    @pytest.fixture
    def test_example_dict(self, test_example: Example) -> Dict[str, Any]:
        """
        Fixture providing the expected dictionary representation of the test example.

        Args:
            test_example: The test Example instance to create the dict for

        Returns:
            Dict[str, Any]: The expected dictionary representation with class information
        """
        return {
            "pipe_code": "extract_gantt_by_steps",
            "output_concept": "",
            "memory": [
                {
                    "stuff_code": test_example.memory[0].stuff_code,
                    "pipelex_session_id": test_example.memory[0].pipelex_session_id,
                    "creation_record": None,
                    "stuff_name": "gantt_chart_image",
                    "concept_code": "gantt.GanttChartImage",
                    "content": {
                        "url": PipeTestCases.URL_IMG_GANTT_1,
                        "source_prompt": None,
                        "__class__": "ImageContent",
                        "__module__": "pipelex.core.stuff_content",
                    },
                    "__class__": "Stuff",
                    "__module__": "pipelex.core.stuff",
                }
            ],
            "__class__": "Example",
            "__module__": "tests.pipelex.asynch.test_client",
        }

    def test_dump_dict_validate(
        self,
        test_example: Example,
        test_example_dict: Dict[str, Any],
    ):
        """
        Test serialization and deserialization of Example objects using kajson.

        Args:
            test_example: The test Example instance
            test_example_dict: The expected dictionary representation
        """
        test_obj_str = str(test_example_dict).replace("None", "null").replace("'", '"')

        deserialized_str = kajson.dumps(test_example)
        pretty_print(deserialized_str, title="Serialized")
        assert deserialized_str == test_obj_str

        # Validate the dictionary back to a model
        deserialized = kajson.loads(deserialized_str)
        pretty_print(deserialized, title="Deserialized")

        assert test_example == deserialized
