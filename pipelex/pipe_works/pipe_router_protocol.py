# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Protocol

from pipelex.core.pipe_output import PipeOutputType
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata
from pipelex.pipe_works.pipe_job import PipeJob


class PipeRouterProtocol(Protocol):
    async def run_pipe_job(
        self,
        pipe_job: PipeJob,
        wfid: Optional[str] = None,
    ) -> PipeOutputType: ...  # pyright: ignore[reportInvalidTypeVarUse]

    async def run_pipe_code(
        self,
        pipe_code: str,
        pipe_run_params: Optional[PipeRunParams] = None,
        job_metadata: Optional[JobMetadata] = None,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        wfid: Optional[str] = None,
    ) -> PipeOutputType: ...  # pyright: ignore[reportInvalidTypeVarUse]
