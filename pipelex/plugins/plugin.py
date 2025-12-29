from pydantic import BaseModel

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class Plugin(BaseModel):
    sdk: str
    backend: str
    variant: str | None = None

    @property
    def sdk_handle(self) -> str:
        if self.variant:
            return f"{self.sdk}@{self.backend}/{self.variant}"
        else:
            return f"{self.sdk}@{self.backend}"

    @classmethod
    def make_for_inference_model(cls, inference_model: InferenceModelSpec) -> "Plugin":
        return Plugin(
            sdk=inference_model.sdk,
            backend=inference_model.backend_name,
            variant=inference_model.variant,
        )
