# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum


# List of classic Img generation preset handles, for convenience
class ImggHandle(StrEnum):
    FLUX_1_PRO_LEGACY = "fal-ai/flux-pro"
    FLUX_1_1_PRO = "fal-ai/flux-pro/v1.1"
    FLUX_1_1_ULTRA = "fal-ai/flux-pro/v1.1-ultra"
    SDXL_LIGHTNING = "fal-ai/fast-lightning-sdxl"
