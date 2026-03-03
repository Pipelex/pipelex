import json
from typing import Any, cast

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.fetch_worker_abstract import FetchWorkerAbstract
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_exceptions import GatewaySearchResponseError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_search_schemas import GatewayFetchRequestParams


class GatewayFetchWorker(FetchWorkerAbstract):
    """Fetch worker that routes through Portkey to the pipelex-relay LinkUp fetch endpoint."""

    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
    ):
        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided sdk_instance for {self.__class__.__name__} is not of type AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance
        self.inference_model = inference_model
        self._tenacity_config = get_config().cogt.tenacity_config

    def _make_retryer(self) -> AsyncRetrying:
        """Create a fresh AsyncRetrying instance for each call."""
        return AsyncRetrying(
            retry=retry_if_exception(self._is_retryable_portkey_error),
            before_sleep=self._log_retry,
            wait=wait_random_exponential(
                multiplier=self._tenacity_config.wait_multiplier,
                max=self._tenacity_config.wait_max,
                exp_base=self._tenacity_config.wait_exp_base,
            ),
            reraise=True,
            stop=stop_after_attempt(self._tenacity_config.max_retries),
        )

    @override
    async def fetch_url(
        self,
        url: str,
        include_raw_html: bool | None = None,
        render_js: bool | None = None,
        extract_images: bool | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> TextAndImagesContent:
        params = GatewayFetchRequestParams(
            url=url,
            include_raw_html=include_raw_html,
            render_js=render_js,
            extract_images=extract_images,
            timeout=timeout,
        )

        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Fetch via gateway config '{config_id}'")

        messages: list[dict[str, str]] = [{"role": "user", "content": params.model_dump_json()}]

        attempt_number = 0
        response: GenericResponse | None = None
        retryer = self._make_retryer()
        try:
            async for attempt in retryer:
                with attempt:
                    attempt_number += 1
                    response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        "/chat/completions",
                        model="linkup/fetch",
                        messages=messages,
                    )
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            msg = f"Fetch service error after {attempt_number} attempt(s): {error_summary}"
            raise GatewaySearchResponseError(msg) from exc

        if response is None:
            msg = f"Could not get a fetch response via Portkey after {attempt_number} attempts"
            raise GatewaySearchResponseError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        # Extract content from response
        try:
            raw_content = cast("object", response.choices[0].message.content)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        except (AttributeError, IndexError) as exc:
            msg = "Could not extract content from gateway fetch response"
            raise GatewaySearchResponseError(msg) from exc

        if not isinstance(raw_content, str):
            msg = f"Expected string content in fetch response, got {type(raw_content)}"
            raise GatewaySearchResponseError(msg)
        content_str: str = raw_content

        result_dict: dict[str, Any] = json.loads(content_str)

        text = TextContent(text=result_dict["markdown"]) if result_dict.get("markdown") else None

        images: list[ImageContent] | None = None
        if result_dict.get("images") is not None:
            images = [
                ImageContent(
                    url=image["url"],
                    caption=image.get("alt"),
                )
                for image in result_dict["images"]
            ]

        return TextAndImagesContent(
            text=text,
            images=images or None,
            raw_html=result_dict.get("raw_html"),
        )

    def _is_retryable_portkey_error(self, exc: BaseException) -> bool:
        if isinstance(exc, portkey_exceptions.NotFoundError):
            msg = str(exc).lower()
            return "specified deployment could not be found" in msg
        return False

    def _log_retry(self, retry_state: RetryCallState) -> None:
        """Called before sleeping between retries."""
        if not retry_state.outcome:
            log.error("Tenacity retry state outcome is None")
            return
        exc = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0.0
        log.dev(f"{self.__class__.__name__} retry #{attempt} for fetch due to '{type(exc).__name__}'.")
        log.verbose(f"Wait duration before next attempt: {wait_duration:.4f}s")
