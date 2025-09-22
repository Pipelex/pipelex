from google import genai

from pipelex.cogt.model_backends.backend import InferenceBackend


class GoogleFactory:
    @staticmethod
    def make_google_client(backend: InferenceBackend) -> genai.Client:
        """Create a Google Gemini API client."""
        return genai.Client(api_key=backend.api_key)
