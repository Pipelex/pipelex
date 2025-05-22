# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.config import get_config
from pipelex.core.pipe_run_params import BatchParams, PipeOutputMultiplicity, PipeRunParams


class PipeRunParamsFactory:
    @classmethod
    def make_run_params(
        cls,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
        batch_params: Optional[BatchParams] = None,
    ) -> PipeRunParams:
        pipe_stack_limit = get_config().pipelex.pipe_run_config.pipe_stack_limit
        return PipeRunParams(
            pipe_stack_limit=pipe_stack_limit,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
            batch_params=batch_params,
        )
