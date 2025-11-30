import base64
import os

from dotenv import load_dotenv
from portkey_ai import Portkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt, wait_fixed

from pipelex import log, pretty_print
from pipelex.pipelex import Pipelex

load_dotenv()

Pipelex.make()


def is_retryable_portkey_error(exc: BaseException) -> bool:
    if isinstance(exc, portkey_exceptions.NotFoundError):
        msg = str(exc).lower()
        return "specified deployment could not be found" in msg
    return False


def log_retry(retry_state: RetryCallState) -> None:
    """Called before sleeping between retries."""
    if not retry_state.outcome:
        log.error("Retry state outcome is None")
        return
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    log.dev(f"[tenacity] Retry #{attempt} for mistral-document-ai due to: {exc!r}", title="tenacity")


PORTKEY_API_KEY = os.getenv("PIPELEX_GATEWAY_API_KEY")

portkey = Portkey(api_key=PORTKEY_API_KEY, config="pc-misdoc-b4ae47")

with open("data/Job-Offer.pdf", "rb") as pdf_file:
    base64_pdf = base64.b64encode(pdf_file.read()).decode("utf-8")
doc_url = f"data:application/pdf;base64,{base64_pdf}"

retryer = Retrying(
    retry=retry_if_exception(is_retryable_portkey_error),
    before_sleep=log_retry,
    wait=wait_fixed(wait=0.1),
    reraise=True,
    stop=stop_after_attempt(20),
)

for attempt in retryer:
    with attempt:
        response = portkey.post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            "/",
            model="mistral-document-ai-2505",
            document={"type": "document_url", "document_url": doc_url},
            include_image_base64=True,
        )

pretty_print(response)
