# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from pydantic import Field

from pipelex.tools.config.models import ConfigModel


class BedrockClientMethod(StrEnum):
    BOTO3 = "boto3"
    AIBOTO3 = "aioboto3"


class BedrockConfig(ConfigModel):
    aws_region: str
    client_method: BedrockClientMethod = Field(strict=False)
