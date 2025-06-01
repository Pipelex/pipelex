from typing import Any, Dict, Literal, Optional, Union

from pydantic import Field, model_validator
from typing_extensions import Self, override

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Quality
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.pipe_img_gen import PipeImgGen
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeImgGenBlueprint(PipeBlueprint):
    imgg_prompt: Optional[str] = None
    imgg_prompt_stuff_name: Optional[str] = None
    imgg_handle: Optional[ImggHandle] = None
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_moderated: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    nb_output: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_imgg_prompt_and_imgg_prompt_stuff_name(self) -> Self:
        if excess_attributes_list := has_more_than_one_among_attributes_from_lists(
            self,
            [
                ["imgg_prompt", "imgg_prompt_stuff_name"],
                ["quality", "nb_steps"],
            ],
        ):
            raise PipeDefinitionError(f"PipeImgGenBlueprint should have no more than one of {excess_attributes_list} among them")
        return self


class PipeImgGenFactory(PipeSpecificFactoryProtocol[PipeImgGenBlueprint, PipeImgGen]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeImgGenBlueprint,
    ) -> PipeImgGen:
        output_multiplicity = pipe_blueprint.nb_output or 1
        return PipeImgGen(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            input_concept_code=pipe_blueprint.input,
            output_concept_code=pipe_blueprint.output,
            output_multiplicity=output_multiplicity,
            imgg_prompt=pipe_blueprint.imgg_prompt,
            imgg_prompt_stuff_name=pipe_blueprint.imgg_prompt_stuff_name,
            imgg_handle=pipe_blueprint.imgg_handle,
            aspect_ratio=pipe_blueprint.aspect_ratio,
            nb_steps=pipe_blueprint.nb_steps,
            guidance_scale=pipe_blueprint.guidance_scale,
            is_moderated=pipe_blueprint.is_moderated,
            safety_tolerance=pipe_blueprint.safety_tolerance,
            is_raw=pipe_blueprint.is_raw,
            seed=pipe_blueprint.seed,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeImgGen:
        pipe_blueprint = PipeImgGenBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
