import sys
import threading
from types import TracebackType
from typing import TYPE_CHECKING

from pipelex import log

if TYPE_CHECKING:
    # Deferred import: avoid pulling heavy SDK at module-load time
    from posthog import Posthog


class DualClientExceptionCapture:
    """Captures unhandled exceptions and sends them to multiple PostHog clients.

    Unlike PostHog's built-in exception_autocapture which only uses default_client,
    this implementation sends to both custom and Pipelex PostHog clients.
    """

    def __init__(
        self,
        custom_posthog_client: "Posthog | None",
        custom_distinct_id: str | None,
        pipelex_posthog_client: "Posthog | None",
        pipelex_distinct_id: str | None,
    ):
        self._custom_client = custom_posthog_client
        self._custom_distinct_id = custom_distinct_id
        self._pipelex_client = pipelex_posthog_client
        self._pipelex_distinct_id = pipelex_distinct_id

        # Save original hooks
        self._original_excepthook = sys.excepthook
        self._original_threading_excepthook = threading.excepthook

        # Install our hooks
        sys.excepthook = self._exception_handler
        threading.excepthook = self._thread_exception_handler

    def close(self) -> None:
        """Restore original exception hooks."""
        sys.excepthook = self._original_excepthook
        threading.excepthook = self._original_threading_excepthook

    def _exception_handler(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        """Handle uncaught exceptions from main thread."""
        self._capture_exception((exc_type, exc_value, exc_traceback))
        # Always call original handler to preserve default behavior
        self._original_excepthook(exc_type, exc_value, exc_traceback)

    def _thread_exception_handler(self, args: threading.ExceptHookArgs) -> None:
        """Handle uncaught exceptions from threads."""
        self._capture_exception((args.exc_type, args.exc_value, args.exc_traceback))
        # Always call original handler to preserve default behavior (prints to stderr)
        self._original_threading_excepthook(args)

    def _capture_exception(
        self,
        exc_info: tuple[type[BaseException], BaseException | None, TracebackType | None],
    ) -> None:
        """Capture exception to both PostHog clients."""
        exc_type, exc_value, exc_traceback = exc_info

        # Skip if no actual exception value (can happen with threading.excepthook)
        if exc_value is None:
            return

        # Create the properly typed tuple for PostHog
        posthog_exc_info: tuple[type[BaseException], BaseException, TracebackType | None] = (
            exc_type,
            exc_value,
            exc_traceback,
        )

        # Send to custom PostHog client
        if self._custom_client:
            try:
                self._custom_client.capture_exception(posthog_exc_info, distinct_id=self._custom_distinct_id)
            except Exception as capture_exc:  # noqa: BLE001
                log.debug(f"Failed to capture exception to custom PostHog: {capture_exc}")

        # Send to Pipelex PostHog client
        if self._pipelex_client:
            try:
                self._pipelex_client.capture_exception(posthog_exc_info, distinct_id=self._pipelex_distinct_id)
            except Exception as capture_exc:  # noqa: BLE001
                log.debug(f"Failed to capture exception to Pipelex PostHog: {capture_exc}")
