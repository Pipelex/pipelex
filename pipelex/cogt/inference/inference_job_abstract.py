# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from abc import ABC, abstractmethod

from pydantic import BaseModel

from pipelex.job_metadata import JobMetadata


class InferenceJobAbstract(ABC, BaseModel):
    job_metadata: JobMetadata

    @abstractmethod
    def validate_before_execution(self):
        pass
