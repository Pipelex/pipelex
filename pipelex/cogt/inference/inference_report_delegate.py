# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Protocol

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract


class InferenceReportDelegate(Protocol):
    def report_inference_job(self, inference_job: InferenceJobAbstract): ...

    def general_report(self): ...
