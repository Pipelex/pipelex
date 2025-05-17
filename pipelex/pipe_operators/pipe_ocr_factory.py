# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import pretty_print
from pipelex.cogt.ocr.ocr_engine_factory import OcrEngineName
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.pipe_ocr import PipeOCR
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeOCRBlueprint(PipeBlueprint):
    definition: Optional[str] = None
    image: Optional[str] = None
    pdf: Optional[str] = None
    ocr_engine_name: Optional[OcrEngineName] = None
    output: str

    @model_validator(mode="after")
    def validate_input_source(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image", "pdf"]):
            raise PipeDefinitionError("Either 'image' or 'pdf' must be provided")
        return self


class PipeOCRFactory(PipeSpecificFactoryProtocol[PipeOCRBlueprint, PipeOCR]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeOCRBlueprint,
    ) -> PipeOCR:
        return PipeOCR(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            ocr_engine_name=pipe_blueprint.ocr_engine_name,
            output_concept_code=pipe_blueprint.output,
            image_stuff_name=pipe_blueprint.image,
            pdf_stuff_name=pipe_blueprint.pdf,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeOCR:
        pipe_blueprint = PipeOCRBlueprint.model_validate(details_dict)
        pretty_print(pipe_blueprint, title="pipe_blueprint")
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
