# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict

from typing_extensions import override

from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.pipe_operators.pipe_func import PipeFunc


class PipeFuncBlueprint(PipeBlueprint):
    function_name: str


class PipeFuncFactory(PipeSpecificFactoryProtocol[PipeFuncBlueprint, PipeFunc]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeFuncBlueprint,
    ) -> PipeFunc:
        return PipeFunc(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            input_concept_code=pipe_blueprint.input,
            output_concept_code=pipe_blueprint.output,
            function_name=pipe_blueprint.function_name,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeFunc:
        pipe_blueprint = PipeFuncBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
