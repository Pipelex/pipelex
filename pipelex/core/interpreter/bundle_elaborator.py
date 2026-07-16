from typing import TypeGuard

from pydantic import ValidationError

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundles.pipelex_bundle_blueprint import (
    ElaborationMetadata,
    PipeBlueprintUnion,
    PipelexBundleBlueprint,
    StepRole,
)
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.interpreter.exceptions import BundleElaboratorError
from pipelex.core.pipes.validation import is_pipe_code_valid
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint

_SYNTHETIC_DRAFT_TEXT_SUFFIX = "__draft_text"
_SYNTHETIC_STRUCTURE_SUFFIX = "__structure"


def _is_preliminary_text_pipe(pipe_blueprint: PipeBlueprintUnion) -> TypeGuard[PipeLLMBlueprint]:
    """Return True iff `pipe_blueprint` is a PipeLLMBlueprint carrying `structuring_method = preliminary_text`.

    Declared as a TypeGuard so callers (including the iteration below) can pass the narrowed
    PipeLLMBlueprint to helpers without casts.
    """
    if not isinstance(pipe_blueprint, PipeLLMBlueprint):
        return False
    method = pipe_blueprint.structuring_method
    return method is not None and method.is_preliminary_text


class BundleElaborator:
    """Rewrites build-time directives on a `PipelexBundleBlueprint` into concrete pipe trees.

    Today the elaborator handles a single directive: `structuring_method = preliminary_text` on
    `PipeLLMBlueprint`, which is rewritten into `PipeSequence[PipeLLM(text), PipeStructure]`.
    The synthesized pipes are recorded in `bundle.elaboration_metadata` so downstream tools can
    surface them differently from user-authored pipes.
    """

    @classmethod
    def elaborate(cls, bundle: PipelexBundleBlueprint) -> PipelexBundleBlueprint:
        if not bundle.pipe or not any(_is_preliminary_text_pipe(blueprint) for blueprint in bundle.pipe.values()):
            return bundle

        existing_codes: set[str] = set(bundle.pipe.keys())
        new_pipe_dict: dict[str, PipeBlueprintUnion] = {}
        elaboration_metadata: dict[str, ElaborationMetadata] = {}

        for pipe_code, pipe_blueprint in bundle.pipe.items():
            if _is_preliminary_text_pipe(pipe_blueprint):
                cls._elaborate_preliminary_text(
                    pipe_code=pipe_code,
                    pipe_blueprint=pipe_blueprint,
                    new_pipe_dict=new_pipe_dict,
                    elaboration_metadata=elaboration_metadata,
                    existing_codes=existing_codes,
                )
            else:
                new_pipe_dict[pipe_code] = pipe_blueprint

        # Defense in depth: synthesized pipes must never themselves carry the directive.
        # Today this is unreachable (synthesis explicitly sets structuring_method=None),
        # but the guard protects us if a future elaboration kind copies fields wholesale.
        for synthetic_code, synthetic_blueprint in new_pipe_dict.items():
            if synthetic_code in elaboration_metadata and _is_preliminary_text_pipe(synthetic_blueprint):
                msg = (
                    f"Synthesized pipe '{synthetic_code}' carries `structuring_method = preliminary_text`. "
                    "The elaborator should never produce nested directives — this is a bug."
                )
                raise PipelexUnexpectedError(msg)

        elaborated = bundle.model_copy(
            update={
                "pipe": new_pipe_dict,
                "elaboration_metadata": elaboration_metadata,
            },
        )

        # Re-run bundle-level validators against the synthetic pipes so any reference rot
        # surfaces with bundle context, not deep inside library_manager. Because
        # `elaboration_metadata` is declared `Field(exclude=True)` on PipelexBundleBlueprint,
        # `model_dump` strips it before the round-trip — that's intentional: this is a pure
        # pipe/concept-reference check, not a metadata round-trip. The validated instance
        # is therefore discarded; callers receive `elaborated` (which still carries the
        # side-table from the `model_copy` above).
        try:
            _ = PipelexBundleBlueprint.model_validate(elaborated.model_dump(by_alias=True))
        except ValidationError as exc:
            msg = (
                f"Bundle elaboration produced an invalid bundle (domain '{bundle.domain}'). "
                f"Synthetic pipes: {sorted(elaboration_metadata.keys())}. {exc}"
            )
            raise PipelexUnexpectedError(msg) from exc

        return elaborated

    @classmethod
    def _elaborate_preliminary_text(
        cls,
        *,
        pipe_code: str,
        pipe_blueprint: PipeLLMBlueprint,
        new_pipe_dict: dict[str, PipeBlueprintUnion],
        elaboration_metadata: dict[str, ElaborationMetadata],
        existing_codes: set[str],
    ) -> None:
        # Pre-check: output must NOT be Text (catching `Text`, `native.Text`, `Text[]`, `Text[N]`).
        # A domain concept that refines Text gets caught later, at validate_output_with_library time;
        # at the bundle layer we only have strings.
        output_parse_result = parse_concept_with_multiplicity(pipe_blueprint.output)
        if QualifiedRef.parse(output_parse_result.concept_ref_or_code).local_code == NativeConceptCode.TEXT:
            msg = (
                f"Pipe '{pipe_code}': `structuring_method = preliminary_text` cannot be used with output `{pipe_blueprint.output}`. "
                "The output must be a structured concept, not Text."
            )
            raise BundleElaboratorError(msg)

        draft_text_code = f"{pipe_code}{_SYNTHETIC_DRAFT_TEXT_SUFFIX}"
        structure_code = f"{pipe_code}{_SYNTHETIC_STRUCTURE_SUFFIX}"

        if not is_pipe_code_valid(pipe_code=draft_text_code) or not is_pipe_code_valid(pipe_code=structure_code):
            msg = (
                f"Pipe '{pipe_code}': cannot synthesize step pipes — derived codes "
                f"'{draft_text_code}' / '{structure_code}' are not valid snake_case pipe codes. "
                "Shorten the original pipe code."
            )
            raise BundleElaboratorError(msg)

        if draft_text_code in existing_codes or structure_code in existing_codes:
            msg = (
                f"Pipe '{pipe_code}': cannot elaborate — synthetic pipe codes "
                f"'{draft_text_code}' / '{structure_code}' collide with existing pipes in the bundle."
            )
            raise BundleElaboratorError(msg)

        # --- step 1: PipeLLM that produces a single Text draft ---
        # Image variables on the original prompt naturally flow only here, since step-2's prompt
        # template is the canned `structuring_prompt` which references only `{{ text }}`.
        draft_blueprint = PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description=f"Draft text for {pipe_code}",
            inputs=dict(pipe_blueprint.inputs) if pipe_blueprint.inputs else None,
            output="Text",
            system_prompt=pipe_blueprint.system_prompt,
            prompt=pipe_blueprint.prompt,
            model=pipe_blueprint.model,
            model_to_structure=None,
            structuring_method=None,
        )

        # --- step 2: PipeStructure that turns the draft Text into the original structured output ---
        structure_blueprint = PipeStructureBlueprint(
            type="PipeStructure",
            pipe_category="PipeOperator",
            description=f"Structure step for {pipe_code}",
            inputs={"draft_text": "Text"},
            output=pipe_blueprint.output,
            model=pipe_blueprint.model_to_structure,
        )

        # --- wrapping sequence keyed at the original pipe_code ---
        wrapping_sequence = PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description=pipe_blueprint.description,
            inputs=dict(pipe_blueprint.inputs) if pipe_blueprint.inputs else None,
            output=pipe_blueprint.output,
            steps=[
                SubPipeBlueprint(pipe=draft_text_code, result="draft_text"),
                SubPipeBlueprint(pipe=structure_code, result=pipe_code),
            ],
        )

        new_pipe_dict[pipe_code] = wrapping_sequence
        new_pipe_dict[draft_text_code] = draft_blueprint
        new_pipe_dict[structure_code] = structure_blueprint

        elaboration_metadata[draft_text_code] = ElaborationMetadata(parent_pipe_code=pipe_code, step_role=StepRole.DRAFT_TEXT)
        elaboration_metadata[structure_code] = ElaborationMetadata(parent_pipe_code=pipe_code, step_role=StepRole.STRUCTURE)
