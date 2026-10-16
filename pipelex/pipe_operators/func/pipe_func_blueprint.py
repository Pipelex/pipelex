from typing import Literal

from mthds.method_tree.tree_path import nfc
from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.pipe_operators.func.function_name import function_name_form_violation


class PipeFuncBlueprint(PipeBlueprint):
    type: Literal["PipeFunc"] = "PipeFunc"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    function_name: str = Field(
        description=(
            "The import path of the function to call, from the root of the method tree: the module's dotted path, then the "
            "function's name, such as 'funcs.totals.compute_totals' for the function compute_totals of funcs/totals.py. "
            "The function must be a top-level def or async def of that module, decorated with @pipe_func()."
        ),
        json_schema_extra={"pattern": r"^[^.]+(\.[^.]+)+$"},
    )

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, function_name: object) -> object:
        """Refuse a `function_name` that is not an import path, a flat registry key included, and keep it in NFC."""
        if not isinstance(function_name, str):
            return function_name
        violation = function_name_form_violation(function_name=function_name)
        if violation is not None:
            raise ValueError(violation)
        return nfc(function_name)

    @override
    def validate_inputs(self):
        pass

    @override
    def validate_output(self):
        pass
