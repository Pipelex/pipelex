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
        if "/" not in imgg_handle:
            raise ImggEngineFactoryError(f"Invalid Imgg handle: {imgg_handle}. Expected format: platform/model_name")

        # split at the first "/"
        parts = imgg_handle.split("/", 1)

        try:
            imgg_platform = ImggPlatform(parts[0])
        except ValueError:
            raise ImggEngineFactoryError(f"Unknown Imgg platform:' {parts[0]}' extracted from handle '{imgg_handle}'")

        imgg_model_name = parts[1]

        return ImggEngine(imgg_platform=imgg_platform, imgg_model_name=imgg_model_name)
