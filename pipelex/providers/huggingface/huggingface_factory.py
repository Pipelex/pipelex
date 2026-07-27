from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T


class HuggingFaceFactory:
    @classmethod
    def make_huggingface_inference_provider(cls, provider_str: str) -> PROVIDER_OR_POLICY_T:
        match provider_str:
            case "black-forest-labs":
                return "black-forest-labs"
            case "cerebras":
                return "cerebras"
            case "clarifai":
                return "clarifai"
            case "cohere":
                return "cohere"
            case "fal-ai":
                return "fal-ai"
            case "featherless-ai":
                return "featherless-ai"
            case "fireworks-ai":
                return "fireworks-ai"
            case "groq":
                return "groq"
            case "hf-inference":
                return "hf-inference"
            case "hyperbolic":
                return "hyperbolic"
            case "nebius":
                return "nebius"
            case "novita":
                return "novita"
            case "nscale":
                return "nscale"
            case "openai":
                return "openai"
            case "publicai":
                return "publicai"
            case "replicate":
                return "replicate"
            case "sambanova":
                return "sambanova"
            case "scaleway":
                return "scaleway"
            case "together":
                return "together"
            case "zai-org":
                return "zai-org"
            case "auto":
                return "auto"
            case _:
                msg = f"Unknown HuggingFace inference provider: {provider_str}"
                raise ValueError(msg)
