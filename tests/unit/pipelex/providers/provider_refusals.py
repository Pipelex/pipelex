"""Each provider's refusal, raised by its real SDK from a canned HTTP answer, for the refusal-classification tests.

Every helper builds the provider's own client against a transport that answers every request with the given body and
status, so the exception a test classifies is the one a worker would catch, with the message the SDK renders and the
body it keeps.
"""

from __future__ import annotations

from typing import Any

import anthropic
import botocore.session
import httpx
import openai
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from google.genai import errors as genai_errors
from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from mistralai.client.models import UserMessage

ORIGIN = "https://provider.example.com"

# The body of a provider's refusal, as its API sends it.
Body = dict[str, Any]


def answering(*, body: Body, status_code: int = 400) -> httpx.MockTransport:
    """A transport whose every request the provider answers with the status, a 400 unless told, carrying the body."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, json=body, request=request)

    return httpx.MockTransport(handle)


def openai_refusal(body: Body) -> BaseException:
    with httpx.Client(transport=answering(body=body)) as http_client:
        client = openai.OpenAI(api_key="unused-in-this-test", base_url=f"{ORIGIN}/v1", max_retries=0, http_client=http_client)
        with pytest.raises(openai.BadRequestError) as exc_info:
            client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def anthropic_refusal(body: Body) -> BaseException:
    with httpx.Client(transport=answering(body=body)) as http_client:
        client = anthropic.Anthropic(api_key="unused-in-this-test", base_url=ORIGIN, max_retries=0, http_client=http_client)
        with pytest.raises(anthropic.BadRequestError) as exc_info:
            client.messages.create(model="claude-sonnet-4-5", max_tokens=8192, messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def openai_compatible_refusal(*, body: Body, status_code: int) -> BaseException:
    """An OpenAI-compatible server, a gateway, answering with another 4xx than 400, raised by the OpenAI SDK."""
    with httpx.Client(transport=answering(body=body, status_code=status_code)) as http_client:
        client = openai.OpenAI(api_key="unused-in-this-test", base_url=f"{ORIGIN}/v1", max_retries=0, http_client=http_client)
        with pytest.raises(openai.APIStatusError) as exc_info:
            client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def anthropic_status_refusal(*, body: Body, status_code: int) -> BaseException:
    """Anthropic answering with the status, raised by the Anthropic SDK as whichever status error it maps it to."""
    with httpx.Client(transport=answering(body=body, status_code=status_code)) as http_client:
        client = anthropic.Anthropic(api_key="unused-in-this-test", base_url=ORIGIN, max_retries=0, http_client=http_client)
        with pytest.raises(anthropic.APIStatusError) as exc_info:
            client.messages.create(model="claude-sonnet-4-5", max_tokens=8192, messages=[{"role": "user", "content": "Summarize the contract."}])
    return exc_info.value


def mistral_refusal(body: Body) -> BaseException:
    with httpx.Client(transport=answering(body=body)) as http_client:
        client = Mistral(api_key="unused-in-this-test", server_url=ORIGIN, client=http_client)
        with pytest.raises(MistralError) as exc_info:
            client.chat.complete(model="mistral-large-latest", messages=[UserMessage(content="Summarize the contract.")])
    return exc_info.value


def gemini_refusal(body: Body) -> BaseException:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent")
    with pytest.raises(genai_errors.ClientError) as exc_info:
        genai_errors.APIError.raise_for_response(httpx.Response(status_code=400, json=body, request=request))  # pyright: ignore[reportUnknownMemberType]
    return exc_info.value


def bedrock_refusal(message: str) -> BaseException:
    """Bedrock's Converse refusal with the message, raised by a real bedrock-runtime client from a stubbed answer."""
    # The bedrock-runtime client botocore builds from its service model, whose operations it types as nothing
    client: Any = botocore.session.get_session().create_client(
        "bedrock-runtime", region_name="us-east-1", aws_access_key_id="unused-in-this-test", aws_secret_access_key="unused-in-this-test"
    )
    stubber = Stubber(client)
    stubber.add_client_error("converse", service_error_code="ValidationException", service_message=message, http_status_code=400)
    with stubber, pytest.raises(ClientError) as exc_info:
        client.converse(modelId="anthropic.claude-sonnet-4-5", messages=[{"role": "user", "content": [{"text": "Summarize the contract."}]}])
    return exc_info.value
