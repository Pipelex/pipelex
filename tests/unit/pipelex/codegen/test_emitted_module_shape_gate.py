import pytest

from pipelex.codegen.emitters.python_common import refuse_unexpected_python_module_shape
from pipelex.codegen.exceptions import CodegenEmissionError


class TestEmittedModuleShapeGate:
    """The gate admits the emitted shape and refuses any other statement."""

    def test_header_alone_is_admitted(self):
        """A projection with nothing to emit is its header comment alone, which the gate admits."""
        refuse_unexpected_python_module_shape("# a header\n")

    def test_emitted_shape_is_admitted(self):
        """Imports, then classes of a docstring, annotated fields and a `model_config`, are admitted."""
        refuse_unexpected_python_module_shape(
            "from __future__ import annotations\n\nfrom pydantic import BaseModel, ConfigDict, Field\n\n\n"
            'class Thing(BaseModel):\n    """A thing."""\n\n    name: str = Field(..., description="a name")\n\n\n'
            'class Opaque(BaseModel):\n    """Opaque."""\n\n    model_config = ConfigDict(extra="allow")\n'
        )

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param("import os\n", id="plain-import"),
            pytest.param("__import__('os')\n", id="expression-statement"),
            pytest.param('class Thing:\n    """A thing."""\n\n\nvalue = 1\n', id="assignment-after-a-class"),
            pytest.param('class Thing:\n    """A thing."""\n\n    __import__("os")\n', id="statement-in-a-class"),
            pytest.param('class Thing:\n    """A thing."""\n\n    other = 1\n', id="unadmitted-class-assignment"),
            pytest.param('@decorate\nclass Thing:\n    """A thing."""\n', id="decorated-class"),
            pytest.param("def run():\n    pass\n", id="function"),
            pytest.param("class Thing:\n    name: str = Field(...)\n", id="class-without-docstring"),
        ],
    )
    def test_other_statements_are_refused(self, body: str):
        """Any statement the emitters never write is refused."""
        with pytest.raises(CodegenEmissionError):
            refuse_unexpected_python_module_shape(body)

    def test_module_that_does_not_parse_is_refused(self):
        """A module that does not parse is refused as an emission fault."""
        with pytest.raises(CodegenEmissionError, match="does not parse"):
            refuse_unexpected_python_module_shape("class Thing(:\n")
