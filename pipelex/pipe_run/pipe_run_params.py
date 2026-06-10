from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams, check_mock_usage_requires_dry
from pipelex.core.memory.working_memory import BATCH_ITEM_STUFF_NAME, MAIN_STUFF_NAME
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, VariableMultiplicityResolution
from pipelex.pipe_run.pipe_run_mode import PipeRunMode  # noqa: TC001 — pydantic resolves the field annotation at runtime
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.types import Self, StrEnum


class PipeRunParamKey(StrEnum):
    DYNAMIC_OUTPUT_CONCEPT = "_dynamic_output_concept"
    NB_OUTPUT = "_nb_output"

    @classmethod
    def value_list(cls) -> list[str]:
        return [member.value for member in cls]


FORCE_DRY_RUN_MODE_ENV_KEY = "PIPELEX_FORCE_DRY_RUN_MODE"


def output_multiplicity_to_apply(
    base_multiplicity: VariableMultiplicity | None,
    override_multiplicity: VariableMultiplicity | None,
) -> VariableMultiplicityResolution:
    """Resolve output multiplicity settings by combining base configuration with override.

    This function implements a priority system where override values take precedence over
    base values, with clear logic to handle different type combinations and return
    a structured result indicating how output multiplicity should be applied.

    Args:
        base_multiplicity: Base multiplicity setting (from pipe definition).
            - None: Single output (default)
            - True: Multiple outputs (LLM decides count)
            - int: Specific number of outputs
        override_multiplicity: Override multiplicity setting (from runtime params).
            - None: Use base value
            - True: Enable multiple outputs
            - False: Force single output (disable multiplicity)
            - int: Specific number of outputs

    Returns:
        OutputMultiplicityResolution: Structured result containing:
            - resolved_multiplicity: The final multiplicity value to use
            - enable_multiple_outputs: True if multiple outputs should be generated
            - specific_output_count: Exact number of outputs if specified, None otherwise

    Resolution Logic:
        - If override is None: Use base value as-is
        - If override is False: Force single output regardless of base
        - If override is True: Enable multiple outputs, preserve base count if it's int
        - If override is int: Use override count, enable multiple outputs

    Examples:
        >>> result = output_multiplicity_to_apply(None, None)
        >>> (result.resolved_multiplicity, result.enable_multiple_outputs, result.specific_output_count)
        (None, False, None)
        >>> result = output_multiplicity_to_apply(True, None)
        >>> (result.resolved_multiplicity, result.enable_multiple_outputs, result.specific_output_count)
        (True, True, None)
        >>> result = output_multiplicity_to_apply(3, None)
        >>> (result.resolved_multiplicity, result.enable_multiple_outputs, result.specific_output_count)
        (3, True, 3)

    """
    # Case 1: No override provided - use base value as-is
    if override_multiplicity is None:
        if isinstance(base_multiplicity, bool):
            return VariableMultiplicityResolution(
                resolved_multiplicity=base_multiplicity,
                is_multiple_outputs_enabled=base_multiplicity,
                specific_output_count=None,
            )
        elif isinstance(base_multiplicity, int):
            return VariableMultiplicityResolution(
                resolved_multiplicity=base_multiplicity,
                is_multiple_outputs_enabled=True,
                specific_output_count=base_multiplicity,
            )
        else:
            return VariableMultiplicityResolution(
                resolved_multiplicity=base_multiplicity, is_multiple_outputs_enabled=False, specific_output_count=None
            )

    # Case 2: Override is a boolean
    elif isinstance(override_multiplicity, bool):
        if override_multiplicity:
            if isinstance(base_multiplicity, bool):
                return VariableMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None)
            else:
                return VariableMultiplicityResolution(
                    resolved_multiplicity=base_multiplicity,
                    is_multiple_outputs_enabled=True,
                    specific_output_count=base_multiplicity if isinstance(base_multiplicity, int) else None,
                )
        else:
            return VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None)

    else:
        # Case 3: Override is an integer
        return VariableMultiplicityResolution(
            resolved_multiplicity=override_multiplicity,
            is_multiple_outputs_enabled=True,
            specific_output_count=override_multiplicity,
        )


class BatchParams(BaseModel):
    input_list_stuff_name: str
    input_item_stuff_name: str

    @classmethod
    def make_batch_params(
        cls,
        input_list_name: str,
        input_item_name: str,
    ) -> BatchParams:
        return BatchParams(
            input_list_stuff_name=input_list_name,
            input_item_stuff_name=input_item_name,
        )

    @classmethod
    def make_default(cls) -> BatchParams:
        return BatchParams(
            input_list_stuff_name=MAIN_STUFF_NAME,
            input_item_stuff_name=BATCH_ITEM_STUFF_NAME,
        )


class PipeRunParams(BaseModel):
    # `extra="forbid"` so a stale `PipeRunParams(cogt_run_params=...)` constructor fails loudly
    # instead of silently building a LIVE-mode instance (cogt_run_params is derived now, not a field).
    model_config = ConfigDict(extra="forbid")

    # REQUIRED (no default): a payload missing the run mode must fail loud instead of silently
    # running LIVE (the spending direction) or DRY (the mock direction). `frozen=True` because a
    # post-construction DRY→LIVE flip would bypass the validator below and flow straight into
    # real provider spend via the derived carrier — written once at construction by
    # `PipeRunParamsFactory.make_run_params`; operators slice the derived `cogt_run_params` off
    # and thread it into the content-generator protocol so the cogt leaf sees the same mode on
    # any backend.
    run_mode: PipeRunMode = Field(frozen=True)

    # Internal sub-flag of DRY — only CLI access is the hidden `--mock-usage` test trigger
    # (requires `--dry-run`, not shown in --help): when True, the dry LLM leaves report
    # *non-zero* synthetic usage so the end-of-run cost report renders — the cheap, deterministic
    # cross-worker cost-report validation affordance. Rejected on a LIVE run (validator below);
    # frozen for the same reason as `run_mode`.
    is_mock_usage: bool = Field(default=False, frozen=True)

    final_stuff_code: str | None = None
    output_multiplicity: VariableMultiplicity | None = None
    dynamic_output_concept_ref: str | None = None
    batch_params: BatchParams | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    pipe_stack_limit: int
    pipe_stack: list[str] = Field(default_factory=list)
    pipe_layers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mock_usage_requires_dry(self) -> Self:
        check_mock_usage_requires_dry(run_mode=self.run_mode, is_mock_usage=self.is_mock_usage)
        return self

    @property
    def cogt_run_params(self) -> CogtRunParams:
        """Mint the cogt-tier slice of these params — what generators stamp on every assignment.

        Derived (not stored) from the run-mode fields above, so there is exactly one copy of the
        facts; the carrier exists because the cogt layer must stay pipe-agnostic and the assignment
        payloads cross the Temporal activity boundary.
        """
        return CogtRunParams(run_mode=self.run_mode, is_mock_usage=self.is_mock_usage)

    @property
    def pipe_stack_str(self) -> str:
        return ".".join(self.pipe_stack)

    @field_validator("params")
    @classmethod
    def validate_param_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            if key == PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT:
                # TODO: validate the concept code
                pass
            if not key.startswith("_"):
                msg = f"Parameter key '{key}' must start with an underscore '_'"
                raise ValueError(msg)
        return value

    def make_deep_copy(self) -> Self:
        return self.model_copy(deep=True)

    @classmethod
    def copy_by_injecting_multiplicity(
        cls,
        pipe_run_params: Self,
        applied_output_multiplicity: VariableMultiplicity | None,
    ) -> Self:
        """Copy the run params the nb_output into the params, and remove the attribute.
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
        return isinstance(self.output_multiplicity, int) and self.output_multiplicity > 1

    def push_pipe_to_stack(self, pipe_code: str) -> None:
        limit = self.pipe_stack_limit
        if len(self.pipe_stack) >= limit:
            # Check the limit *before* appending: run_pipe() calls push_pipe_to_stack()
            # outside its push/pop try/finally, so a frame appended here on overflow
            # would never be popped and would corrupt the stack of any later reuse.
            msg = f"Exceeded pipe stack limit of {limit}. You can raise that limit in the config. Stack:\n{self.pipe_stack}"
            raise PipeStackOverflowError(message=msg, limit=limit, pipe_stack=self.pipe_stack)
        self.pipe_stack.append(pipe_code)

    def pop_pipe_from_stack(self, pipe_code: str) -> None:
        popped_pipe_code = self.pipe_stack.pop()
        if popped_pipe_code != pipe_code:
            # A mismatch means the push/pop discipline was broken upstream. run_pipe() pushes
            # and pops each frame in a `try`/`finally`, so a frame stays balanced even when its
            # pipe fails — a mismatch here should not happen in normal flow. We log rather than
            # raise: this runs inside run_pipe()'s `finally`, where raising would mask the
            # in-flight exception.
            log.error(f"Pipe code '{pipe_code}' was not the last pipe in the stack, it was '{popped_pipe_code}'")

    def push_pipe_layer(self, pipe_code: str) -> None:
        if self.pipe_layers and self.pipe_layers[-1] == pipe_code:
            return
        self.pipe_layers.append(pipe_code)

    def pop_pipe_code(self) -> str:
        return self.pipe_layers.pop()
