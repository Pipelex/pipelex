# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Protocol

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract


class InferenceReportDelegate(Protocol):
    def open_registry(self, mission_id: str): ...

    def report_inference_job(self, inference_job: InferenceJobAbstract): ...

    def generate_report(self, mission_id: Optional[str] = None): ...

    def close_registry(self, mission_id: str): ...
