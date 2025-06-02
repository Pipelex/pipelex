from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator
from typing_extensions import Self

from pipelex import log
from pipelex.core.working_memory import BATCH_ITEM_STUFF_NAME, MAIN_STUFF_NAME
from pipelex.types import StrEnum


class PipeRunParamKey(StrEnum):
    DYNAMIC_OUTPUT_CONCEPT = "_dynamic_output_concept"
    NB_OUTPUT = "_nb_output"


PipeOutputMultiplicity = Union[bool, int]


def make_output_multiplicity(nb_output: Optional[int], multiple_output: Optional[bool]) -> Optional[PipeOutputMultiplicity]:
    output_multiplicity: Optional[PipeOutputMultiplicity]
    if nb_output:
        output_multiplicity = nb_output
    elif multiple_output:
        output_multiplicity = True
    else:
        output_multiplicity = None
    return output_multiplicity


def output_multiplicity_to_apply(
    output_multiplicity_base: Optional[PipeOutputMultiplicity],
    output_multiplicity_override: Optional[PipeOutputMultiplicity],
) -> Tuple[Optional[PipeOutputMultiplicity], bool, Optional[int]]:
    """
    Interpret / unwrap the output multiplicity override and return the appropriate values.
    """
    log.debug(f"output_multiplicity_base = {output_multiplicity_base}")
    log.debug(f"output_multiplicity_override = {output_multiplicity_override}")
    if output_multiplicity_override is None:
        log.debug("output_multiplicity_override is None")
        if isinstance(output_multiplicity_base, bool):
            log.debug("output_multiplicity_base is bool")
            return output_multiplicity_base, output_multiplicity_base, None
        elif isinstance(output_multiplicity_base, int):
            log.debug("output_multiplicity_base is int")
            return output_multiplicity_base, True, output_multiplicity_base
        else:
            log.debug("output_multiplicity_base is not bool")
            return output_multiplicity_base, False, output_multiplicity_base
    elif isinstance(output_multiplicity_override, bool):
        log.debug("output_multiplicity_override is bool")
        if output_multiplicity_override:
            log.debug("output_multiplicity_override is True")
            if isinstance(output_multiplicity_base, bool):
                log.debug("output_multiplicity_base is bool")
                # base is also bool, we disregard it
                return True, True, None
            else:
                log.debug("output_multiplicity_base is not bool")
                # base is an int, we use it
                return output_multiplicity_base, True, output_multiplicity_base
        else:
            log.debug("output_multiplicity_override is False")
            # override is False, we refuse multiplicity
            return False, False, None
    else:
        log.debug("output_multiplicity_override is int")
        # override is an int, we use it
        return output_multiplicity_override, True, output_multiplicity_override


class BatchParams(BaseModel):
    input_list_stuff_name: str
    input_item_stuff_name: str

    @classmethod
    def make_optional_batch_params(
        cls,
        input_list_name: Union[bool, str],
        input_item_name: Optional[str] = None,
    ) -> Optional["BatchParams"]:
        the_batch_params: Optional[BatchParams] = None
        if input_list_name or input_item_name:
            input_list_stuff_name: str
            if isinstance(input_list_name, str):
                input_list_stuff_name = input_list_name
            else:
                input_list_stuff_name = MAIN_STUFF_NAME
            input_item_stuff_name = input_item_name or BATCH_ITEM_STUFF_NAME
            the_batch_params = BatchParams(
                input_list_stuff_name=input_list_stuff_name,
                input_item_stuff_name=input_item_stuff_name,
            )
        return the_batch_params

    @classmethod
    def make_default(cls) -> "BatchParams":
        return BatchParams(
            input_list_stuff_name=MAIN_STUFF_NAME,
            input_item_stuff_name=BATCH_ITEM_STUFF_NAME,
        )


class PipeRunParams(BaseModel):
    final_stuff_code: Optional[str] = None
    output_multiplicity: Optional[PipeOutputMultiplicity] = None
    dynamic_output_concept_code: Optional[str] = None
    batch_params: Optional[BatchParams] = None
    params: Dict[str, Any] = Field(default_factory=dict)

    pipe_stack_limit: int
    pipe_stack: List[str] = Field(default_factory=list)
    pipe_layers: List[str] = Field(default_factory=list)

    @field_validator("params")
    @classmethod
    def validate_param_keys(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        for key in v:
            if not key.startswith("_"):
                raise ValueError(f"Parameter key '{key}' must start with an underscore '_'")
        return v

    @classmethod
    def copy_by_injecting_multiplicity(
        cls,
        pipe_run_params: Self,
        applied_output_multiplicity: Optional[PipeOutputMultiplicity],
    ) -> Self:
        """
        Copy the run params the nb_output into the params, and remove the attribute.
        This is useful to make a single prompt with multiple outputs.
        """
        new_run_params = pipe_run_params.model_copy()

        # inject the nb_output into the params, and remove the attribute
        if isinstance(applied_output_multiplicity, bool):
            new_run_params.output_multiplicity = applied_output_multiplicity
        elif isinstance(applied_output_multiplicity, int):
            new_run_params.output_multiplicity = False
            new_run_params.params[PipeRunParamKey.NB_OUTPUT] = applied_output_multiplicity
        return new_run_params

    @property
    def is_multiple_output_required(self) -> bool:
        return isinstance(self.output_multiplicity, int) and self.output_multiplicity > 1  # pyright: ignore[reportUnnecessaryIsInstance]

    def push_pipe_to_stack(self, pipe_code: str) -> None:
        self.pipe_stack.append(pipe_code)

    def pop_pipe_from_stack(self, pipe_code: str) -> None:
        popped_pipe_code = self.pipe_stack.pop()
        if popped_pipe_code != pipe_code:
            # raise PipeRunError(f"Pipe code '{pipe_code}' was not the last pipe in the stack, it was '{popped_pipe_code}'")
            log.error(f"Pipe code '{pipe_code}' was not the last pipe in the stack, it was '{popped_pipe_code}'")
            # TODO: investigate how this can happen, maybe due to a shared object between branches of PipeBatch or PipeParallel
            # (which should be copied instead)

    def push_pipe_layer(self, pipe_code: str) -> None:
        if self.pipe_layers and self.pipe_layers[-1] == pipe_code:
            return
        self.pipe_layers.append(pipe_code)

    def pop_pipe_code(self) -> str:
        return self.pipe_layers.pop()
