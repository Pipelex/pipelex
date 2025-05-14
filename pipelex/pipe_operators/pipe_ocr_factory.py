# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional

from typing_extensions import override

from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.pipe_operators.pipe_ocr import PipeOCR


class PipeOCRBlueprint(PipeBlueprint):
    definition: Optional[str] = None
    image_stuff_name: str
    ocr_engine_name: str
    output: str


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
            image_stuff_name=pipe_blueprint.image_stuff_name,
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
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
