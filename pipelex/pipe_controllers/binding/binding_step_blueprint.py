from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, SerializerFunctionWrapHandler, field_validator, model_serializer

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_machinery.validation import BINDING_PATH_PATTERN, BINDING_RESULT_PATTERN
from pipelex.tools.misc.string_utils import FIELD_PATH_SEGMENT_REGEX, SNAKE_CASE_IDENTIFIER_REGEX, is_field_path, is_snake_case
from pipelex.validation_error_types import PipeValidationErrorType

# The key a binding step is recognized by, as MTHDS writes it. `from` is a Python keyword, so the blueprint field is
# `from_path`, as PipeCompose's construct spells it, but that name is Python's only: MTHDS spells the key `from`, and a
# step spelling it `from_path` is refused, as the schema refuses it, while every dump writes `from`.
BINDING_FROM_KEY = "from"

# The fields of a pipe step that a binding step never carries, `result` aside, which both shapes share.
PIPE_STEP_ONLY_FIELDS: tuple[str, ...] = ("pipe", "nb_output", "multiple_output", "batch_over", "batch_as")

# How a message states the path grammar, after "a path is": the grammar of a binding step's `from` and of a dotted `batch_over`.
PATH_GRAMMAR_DESCRIPTION = (
    "a name in working memory followed by zero or more field names, separated by single dots, each a letter followed by letters, "
    f"digits and underscores (`{FIELD_PATH_SEGMENT_REGEX}`), with no subscript, expression, whitespace or underscore-led segment"
)
_RESULT_GRAMMAR = f"a plain input name, a snake_case identifier matching `{SNAKE_CASE_IDENTIFIER_REGEX}`"


def is_binding_step_dict(*, raw_step: Mapping[str, Any]) -> bool:
    """Whether a step, as written, is a binding step: it carries `from`."""
    return BINDING_FROM_KEY in raw_step


def check_binding_step_shape(*, raw_step: Mapping[str, Any], step_label: str) -> None:
    """Refuse a step whose shape breaks the binding-step rules, before it is parsed into either shape.

    A step carries exactly one of `pipe` and `from`; a binding step carries `result` and none of a pipe step's
    other fields. A step carrying neither `pipe` nor `from` is left to the pipe-step shape, which refuses it
    with no error name of its own, as the standard says.

    Raises:
        PipeValidationError: ``BINDING_STEP_INVALID`` naming the fault.
    """
    if not is_binding_step_dict(raw_step=raw_step):
        return
    from_path = raw_step.get(BINDING_FROM_KEY)
    if "pipe" in raw_step:
        msg = (
            f"{step_label} carries both `pipe` and `from`: a step either runs a pipe or binds a value, never both. "
            f'Split it into a binding step `{{ from = "{from_path}", result = "<name>" }}` and a pipe step reading that name.'
        )
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID)
    pipe_step_fields = [field_name for field_name in PIPE_STEP_ONLY_FIELDS if field_name in raw_step]
    if pipe_step_fields:
        quoted_fields = ", ".join(f"`{field_name}`" for field_name in pipe_step_fields)
        msg = (
            f"{step_label} is a binding step (it carries `from`), which carries only `from` and `result`, so it cannot carry {quoted_fields}. "
            f'To batch over the list at `{from_path}`, write it as a pipe step\'s `batch_over = "{from_path}"`, which binds it and batches over '
            "the bound list, or bind it first, then batch over the bound name in the next pipe step."
        )
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID)
    if "result" not in raw_step:
        msg = f"{step_label} is a binding step without `result`: a binding step names the value it binds, so `result` is required."
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID)


class BindingStepBlueprint(BaseModel):
    """A PipeSequence step that binds the value at a path in working memory to a new name.

    `{ from = "invoice.total", result = "total_amount" }` stores a deep copy of the value at `invoice.total`
    under `total_amount`, as the concept the path derives through the declared structures. A binding step
    lives in a PipeSequence's `steps` only, and carries exactly these two fields.
    """

    # No `populate_by_name`: the path is read under `from` alone, so a `from_path` key is refused as an extra field.
    model_config = ConfigDict(extra="forbid")

    from_path: str = Field(
        validation_alias=BINDING_FROM_KEY,
        serialization_alias=BINDING_FROM_KEY,
        description="The path to bind: a name in working memory followed by zero or more field names, separated by dots.",
        json_schema_extra={"pattern": BINDING_PATH_PATTERN},
    )
    result: str = Field(
        description="The name under which the bound value is stored in working memory: a plain input name.",
        json_schema_extra={"pattern": BINDING_RESULT_PATTERN},
    )

    @field_validator("from_path", mode="after")
    @classmethod
    def validate_from_path(cls, from_path: str) -> str:
        if not is_field_path(path=from_path):
            msg = f"The binding step's `from` '{from_path}' is not a path: a path is {PATH_GRAMMAR_DESCRIPTION}."
            raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID, variable_names=[from_path])
        return from_path

    @field_validator("result", mode="after")
    @classmethod
    def validate_result(cls, result: str) -> str:
        if not is_snake_case(result):
            msg = (
                f"The binding step's `result` '{result}' is not {_RESULT_GRAMMAR}: a bound value is read by a later step's input, under a plain name."
            )
            raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.BINDING_STEP_INVALID, variable_names=[result])
        return result

    @model_serializer(mode="wrap")
    def serialize_under_from(self, handler: SerializerFunctionWrapHandler):
        """Always write the path under `from`, the one key the parser reads back, whatever the caller asks.

        A dump without `by_alias` would otherwise write `from_path`, which a crate would carry and hash, and which
        a crate validated again refuses as an extra field. PipeCompose's construct writes `from` the same way.

        The return is deliberately unannotated — see `ConceptBlueprint.serialize_without_absent_hints`:
        an annotation here becomes the model's serialization JSON Schema and erases its shape.
        """
        dumped: dict[str, Any] = handler(self)
        return {(BINDING_FROM_KEY if key == "from_path" else key): value for key, value in dumped.items()}

    @property
    def root_name(self) -> str:
        return self.from_path.split(".", maxsplit=1)[0]


def raw_step_mapping(*, raw_step: Any) -> Mapping[str, Any] | None:
    """A step as written, when it is a table; `None` for an already-parsed blueprint or anything else."""
    if isinstance(raw_step, Mapping):
        return cast("Mapping[str, Any]", raw_step)
    return None
