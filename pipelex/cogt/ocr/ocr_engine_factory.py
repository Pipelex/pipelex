from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_platform import OcrPlatform


class OcrEngineFactoryError(CogtError):
    pass


class OcrEngineFactory:
    @classmethod
    def make_ocr_engine(
        cls,
        ocr_handle: str,
    ) -> OcrEngine:
        parts = ocr_handle.split("/")
        if len(parts) != 2:
            raise OcrEngineFactoryError(f"Invalid Ocr handle: {ocr_handle}")

        try:
            ocr_platform = OcrPlatform(parts[0])
        except ValueError:
            raise OcrEngineFactoryError(f"Invalid Ocr platform: {parts[0]}")

        ocr_model_name = parts[1]

        return OcrEngine(ocr_platform=ocr_platform, ocr_model_name=ocr_model_name)
