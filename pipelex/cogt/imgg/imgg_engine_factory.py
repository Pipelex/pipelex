# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.imgg.imgg_engine import ImggEngine
from pipelex.cogt.imgg.imgg_platform import ImggPlatform


class ImggEngineFactoryError(CogtError):
    pass


class ImggEngineFactory:
    @classmethod
    def make_imgg_engine(
        cls,
        imgg_handle: str,
    ) -> ImggEngine:
        parts = imgg_handle.split("/")
        if len(parts) != 2:
            raise ImggEngineFactoryError(f"Invalid Imgg handle: {imgg_handle}")

        try:
            imgg_platform = ImggPlatform(parts[0])
        except ValueError:
            raise ImggEngineFactoryError(f"Invalid Imgg platform: {parts[0]}")

        imgg_model_name = parts[1]

        return ImggEngine(imgg_platform=imgg_platform, imgg_model_name=imgg_model_name)
