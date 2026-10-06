"""The load-time refusal of an LLM setting the model it resolves to refuses, shared by the operators that generate with one."""

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.models.model_reference import ensure_model_reference
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.kernel.llm_ops import check_llm_setting_with_served_model
from pipelex.runtime_hub import get_model_deck
from pipelex.validation_error_types import PipeValidationErrorType


def refuse_llm_setting_its_model_refuses(
    *,
    pipe_type: str,
    pipe_code: str,
    domain_code: str,
    llm_setting: LLMSetting,
    llm_choice: LLMModelChoice | None,
    field_name: str | None,
    is_structured: bool,
) -> None:
    """Refuse a step's LLM setting when the model it resolves to refuses it for the output the step generates.

    The check is the one the model's worker runs before every call, so a step that would fail at its first
    call, a structured output on a reasoning preset the model cannot take for instance, is refused when the
    method loads, before a run spends anything. A model no backend serves on this boot is left to the run.

    Args:
        pipe_type: The step's pipe type, for the message.
        pipe_code: The step's pipe code.
        domain_code: The step's domain code.
        llm_setting: The setting the step generates with, resolved from its choice or the deck's.
        llm_choice: The choice the step names in `field_name`, or None when the setting is the deck's override or default.
        field_name: The step's field that names the choice, or None when the setting is the deck's override or default.
        is_structured: Whether the step generates a structured output rather than text.

    Raises:
        PipeValidationError: An `llm_setting_refused_by_model` refusal, located on the field that names the setting.

    """
    try:
        check_llm_setting_with_served_model(llm_setting=llm_setting, is_structured=is_structured)
    except LLMCapabilityError as refusal:
        output_desc = "a structured output" if is_structured else "text"
        model_reference: str | None = None
        if llm_choice is None or field_name is None:
            # The deck's chain reads its override before its default, so the remedy names the table that supplied the setting.
            deck_overrides = get_model_deck().llm_choice_overrides
            deck_override = deck_overrides.for_object if is_structured else deck_overrides.for_text
            deck_rung, deck_table = ("override", "llm.choice_overrides") if deck_override is not None else ("default setting", "llm.choice_defaults")
            deck_key = "for_object" if is_structured else "for_text"
            output_kind = "structured outputs" if is_structured else "text"
            setting_desc = f"the model deck's {deck_rung} for {output_kind}"
            remedy = f"Name a model setting in the pipe, or change `{deck_key}` in the deck's `[{deck_table}]`."
        elif isinstance(llm_choice, LLMSetting):
            setting_desc = f"the model setting its `{field_name}` writes inline"
            remedy = f"Change the setting in `{field_name}`, or name a model that takes it."
        else:
            model_reference = ensure_model_reference(llm_choice).raw
            setting_desc = f"the model setting `{model_reference}` its `{field_name}` names"
            remedy = f"Name another setting in `{field_name}`, or one whose model takes it."
        msg = f"{pipe_type} '{pipe_code}' generates {output_desc} with {setting_desc}, which the model it resolves to refuses: {refusal} {remedy}"
        raise PipeValidationError(
            message=msg,
            error_type=PipeValidationErrorType.LLM_SETTING_REFUSED_BY_MODEL,
            domain_code=domain_code,
            pipe_code=pipe_code,
            field_name=field_name,
            model_reference=model_reference,
        ) from refusal
