# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Dict, Optional

from pydantic import BaseModel


class PipeConditionDetails(BaseModel):
    code: str
    test_expression: str
    pipe_map: Dict[str, str]
    default_pipe_code: Optional[str] = None

    evaluated_expression: str
    chosen_pipe_code: str
