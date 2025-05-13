# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pydantic import BaseModel, Field

from pipelex.core.pipe import PipeAbstract
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata


class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: Optional[str] = None
