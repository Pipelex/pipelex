from pydantic import BaseModel

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class Plugin(BaseModel):
    sdk: str
    backend: str

    @property
    def sdk_handle(self) -> str:
        return f"{self.sdk}@{self.backend}"

    @classmethod
    def make_for_inference_model(cls, inference_model: InferenceModelSpec) -> "Plugin":
        return Plugin(
            sdk=inference_model.sdk,
            backend=inference_model.backend_name,
        )
