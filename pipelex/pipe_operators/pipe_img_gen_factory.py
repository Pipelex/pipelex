# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Literal, Optional, Union

from pydantic import Field
from typing_extensions import override

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.pipe_operators.pipe_img_gen import PipeImgGen


class PipeImgGenBlueprint(PipeBlueprint):
    imgg_handle: Optional[ImggHandle] = None
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_safety_checker_enabled: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    nb_output: Optional[int] = Field(default=None, ge=1)


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
            imgg_handle=pipe_blueprint.imgg_handle,
            aspect_ratio=pipe_blueprint.aspect_ratio,
            nb_steps=pipe_blueprint.nb_steps,
            guidance_scale=pipe_blueprint.guidance_scale,
            is_safety_checker_enabled=pipe_blueprint.is_safety_checker_enabled,
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
