import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator, cast

import posthog
from opentelemetry.trace import Tracer as OTelTracer
from posthog import Posthog, new_context  # type: ignore[attr-defined]
from posthog.args import ExceptionArg, OptionalCaptureArgs
from typing_extensions import Unpack, override

from pipelex import log
from pipelex.system.caller_identity import CallerIdentity, get_current_caller_identity
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.exceptions import TelemetryApiKeyMissingError
from pipelex.system.telemetry.otel_constants import OTelConstants, PostHogAttr, PostHogEvent
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.posthog_error_tracker import PostHogErrorTracker
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig, TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy, StreamIdentityRule, TelemetryIdentity
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.error_fields import error_fields

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider

    from pipelex.system.job_metadata import RunMetadata


# What PostHog writes into each frame of an `$exception` beside the module, function and line: the source lines around
# the frame, which may hold a literal of the caller's data or a secret, and the path of the file on this machine.
EXCEPTION_FRAME_SOURCE_KEYS = ("pre_context", "context_line", "post_context", "abs_path", "code_variables")


def strip_exception_frame_sources(  # kw-only: ignore — PostHog before_send callback, invoked positionally
    event: dict[str, Any],
) -> dict[str, Any]:
    """PostHog's `before_send` for the operator's client: an `$exception` leaves with its frames' sources stripped.

    The SDK serializes each frame with the source lines around it and the absolute path of its file, and the
    variables of its frames when asked to, none of which an error report may carry; what stays is the module, the
    function and the line, which is what groups an issue. Any other event goes out untouched.
    """
    if event.get("event") != PostHogEvent.EXCEPTION:
        return event
    for frame in _exception_event_frames(event=event):
        for key in EXCEPTION_FRAME_SOURCE_KEYS:
            frame.pop(key, None)
    return event


def _exception_event_frames(*, event: dict[str, Any]) -> list[dict[str, Any]]:
    """The frames of every exception of an `$exception` event, as the SDK serialized them; anything malformed is skipped."""
    properties = _as_dict(value=event.get("properties"))
    frames: list[dict[str, Any]] = []
    for exception_entry in _as_list(value=properties.get(PostHogAttr.EXCEPTION_LIST)):
        stacktrace = _as_dict(value=_as_dict(value=exception_entry).get("stacktrace"))
        for frame in _as_list(value=stacktrace.get("frames")):
            if isinstance(frame, dict):
                frames.append(cast("dict[str, Any]", frame))
    return frames


def _as_dict(*, value: object) -> dict[str, Any]:
    """``value`` when it is a dict, else an empty one: what a serialized event holds is read without trusting its shape."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _as_list(*, value: object) -> list[Any]:
    """``value`` when it is a list, else an empty one."""
    return cast("list[Any]", value) if isinstance(value, list) else []


class TelemetryManager(TelemetryManagerAbstract):
    PRIVACY_NOTICE = "[Privacy: exception message redacted]"

    def __init__(self, telemetry_config: TelemetryConfig):
        """Initialize the TelemetryManager with the user's own telemetry destinations.

        Args:
            telemetry_config: User's telemetry configuration.
        """
        self.telemetry_config = telemetry_config

        # Create the PostHog client only if the user's event tracking is enabled
        self.custom_posthog_client: Posthog | None = None
        if telemetry_config.custom_posthog.mode.is_enabled:
            if not telemetry_config.custom_posthog.api_key:
                msg = "Custom PostHog is enabled in the telemetry configuration, but its API key is not set"
                raise TelemetryApiKeyMissingError(msg)
            self.custom_posthog_client = Posthog(
                project_api_key=telemetry_config.custom_posthog.api_key,
                host=telemetry_config.custom_posthog.endpoint,
                disable_geoip=not telemetry_config.custom_posthog.geoip,
                debug=telemetry_config.custom_posthog.debug,
                on_error=self._handle_transmission_error,
                before_send=strip_exception_frame_sources,
            )

        # Create OTel tracer for AI tracing if enabled
        self._otel_tracer: OTelTracer | None
        self._tracer_provider: OTelTracerProvider | None
        if telemetry_config.custom_posthog.tracing.enabled:
            # Create redaction config from user settings
            custom_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(posthog_config=telemetry_config.custom_posthog)
            self._otel_tracer, self._tracer_provider = OtelFactory.make_ai_tracer(
                custom_fallback_distinct_id=telemetry_config.custom_posthog.user_id,
                custom_run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=telemetry_config.custom_posthog.mode),
                custom_posthog_client=self.custom_posthog_client,
                custom_redaction_config=custom_redaction_config,
                otlp_exporters=telemetry_config.otlp,
                langfuse_config=telemetry_config.langfuse,
            )
            log.verbose("AI tracing is enabled, and an OpenTelemetry tracer was made")
        else:
            self._otel_tracer = None
            self._tracer_provider = None
            log.verbose("AI tracing is disabled, and no OpenTelemetry tracer was made")

        # Wrap capture_exception to sanitize before sending
        if self.custom_posthog_client:
            self._wrap_capture_exception(self.custom_posthog_client)

        # Set global PostHog settings
        posthog.privacy_mode = True
        posthog.default_client = self.custom_posthog_client

    @override
    def make_error_tracker(self) -> PostHogErrorTracker | None:
        """The ``posthog`` error tracker over the operator's client, with the stream's identity rule, or ``None`` with no client.

        An exception is attributed when it is reported, not here: the tracker reads back the caller of the pipe run
        the error escaped from, and falls back to the stream's own id only for an error that belongs to no caller.
        What is fixed here is the stream's rule, taken from the same settings as every other capture on it, which is
        what carries `anonymous` mode onto this path: a stream that identifies nobody must not identify somebody when
        the process crashes.
        """
        if self.custom_posthog_client is None:
            return None
        return PostHogErrorTracker(
            posthog_client=self.custom_posthog_client,
            identity_rule=StreamIdentityRule(
                fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=self.telemetry_config.custom_posthog.mode),
            ),
        )

    def _handle_transmission_error(  # kw-only: ignore — PostHog on_error callback, invoked positionally as (error, items)
        self, error: Exception | None, items: list[dict[str, Any]]
    ) -> None:
        """Handle errors that occur during custom telemetry transmission.

        A warning rather than an error: the run the events describe is unaffected, and what was
        lost is the operator's own telemetry, whose endpoint or key is what to check. The callback
        runs outside any `except` block, so the exception rides as fields; the items are counted,
        never logged, since they are the events' own properties.

        Args:
            error: The transmission error that occurred
            items: List of telemetry items that failed to send
        """
        if error:
            log.warning("Telemetry events could not be sent to PostHog", fields={"event_count": len(items), **error_fields(exc=error)})

    def _wrap_capture_exception(self, client: Posthog) -> None:
        """Wrap a PostHog client's capture_exception method to sanitize exception messages.

        Args:
            client: The PostHog client to wrap.
        """
        original_capture_exception = client.capture_exception

        def sanitized_capture_exception(
            exception: ExceptionArg | None = None,
            **kwargs: Unpack[OptionalCaptureArgs],
        ) -> Any:
            """Capture an exception with every message along its chain replaced by the privacy notice.

            PostHog marks what it sent so a second capture of the same error is
            dropped, and what it sent may be a redacted copy rather than the
            error the caller holds. The mark is carried back onto the original,
            so the guard still works for a caller that captures an error and
            then lets it escape. Given nothing, PostHog would read the error
            being handled for itself, so that error is resolved first: both the
            check and the mark need it, and `None` can carry neither.

            PostHog's own `capture_exception` never raises into its caller, and
            the redaction in front of it must not either. An argument the SDK
            would decline, or a chain too deep to copy, drops the capture with a
            debug line: sending the original in its place is the one fallback
            that is not open, since it is what the redaction exists to stop.
            """
            try:
                resolved = self._resolved_exception_arg(exception=exception)
                if resolved is None or PostHogErrorTracker.is_marked_as_captured(exception=resolved):
                    return None
                sanitized = self._sanitized_exception_arg(exception=resolved)
            except Exception as sanitize_exc:  # ruff: ignore[blind-except]
                log.debug("An exception capture the privacy redaction could not complete was dropped", fields=error_fields(exc=sanitize_exc))
                return None
            result = original_capture_exception(sanitized, **kwargs)
            PostHogErrorTracker.carry_capture_marks(source=sanitized, target=resolved)
            return result

        client.capture_exception = sanitized_capture_exception  # type: ignore[method-assign]

    @classmethod
    def _resolved_exception_arg(cls, *, exception: ExceptionArg | None) -> ExceptionArg | None:
        """Return `exception`, or when it is `None` the error being handled, which is what PostHog would read for itself.

        Resolved here rather than left to the SDK so the error can still be
        redacted, and so the capture mark lands on the error the caller holds.
        """
        if exception is not None:
            return exception
        current_type, current_value, current_traceback = sys.exc_info()
        if current_type is None or current_value is None:
            return None
        return (current_type, current_value, current_traceback)

    @classmethod
    def _sanitized_exception_arg(cls, *, exception: ExceptionArg) -> ExceptionArg:
        """Return what may go out in place of `exception`, in whichever form PostHog was handed.

        PostHog takes an error either bare or as the `(type, value, traceback)`
        triple an interpreter excepthook receives. And it does not send one
        exception: it walks `__cause__`, `__context__` and the members of an
        exception group, and sends the message of every error it reaches. Any
        of those messages may repeat what the caller passed in: a `PipelexError`
        quotes the path it was reading or a slice of the document that would not
        parse, a `ValueError` a function raised quotes the value it refused, and
        a pydantic `ValidationError` renders the input it rejected. So every
        message in that graph is replaced by the privacy notice, whatever the
        error's class, and what goes out is each error's class and its frames.
        """
        if isinstance(exception, BaseException):
            return cls._redacted_exception_graph(exception=exception)
        _, exception_value, exception_traceback = exception
        if exception_value is None:
            return exception
        redacted_value = cls._redacted_exception_graph(exception=exception_value)
        return (type(redacted_value), redacted_value, exception_traceback)

    @classmethod
    def _redacted_exception_graph(cls, *, exception: BaseException) -> BaseException:
        """Return a copy of everything PostHog would walk from `exception`, every message replaced by the privacy notice.

        The copy has the shape of the original, links and group members
        included, so PostHog walks it as it would have walked the original. It
        is never written back: the live exception is the one the interpreter
        goes on to print and a host may still be holding.

        Built with loops and not a recursion, as PostHog's own walk is: the SDK
        sends a chain as long as the recursion limit, and the redaction in
        front of it must not be what fails on it.
        """
        graph = cls._exception_graph(exception=exception)
        copies: dict[int, BaseException] = {}
        for original in graph:
            if not isinstance(original, BaseExceptionGroup):
                copies[id(original)] = cls._redacted_stand_in(exception=original)
        for group in cls._groups_members_first(graph=graph):
            members = [copies[id(member)] for member in cls._group_members(exception=group) if id(member) in copies]
            copies[id(group)] = cls._redacted_group_stand_in(group=group, members=members)
        for original in graph:
            copied = copies[id(original)]
            copied.__traceback__ = original.__traceback__
            copied.__cause__ = copies.get(id(original.__cause__)) if original.__cause__ is not None else None
            copied.__context__ = copies.get(id(original.__context__)) if original.__context__ is not None else None
            copied.__suppress_context__ = original.__suppress_context__
        return copies[id(exception)]

    @classmethod
    def _exception_graph(cls, *, exception: BaseException) -> list[BaseException]:
        """Every exception PostHog would reach from `exception`, `exception` first, each once."""
        graph: list[BaseException] = []
        pending: list[BaseException | None] = [exception]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current is None or id(current) in visited:
                continue
            visited.add(id(current))
            graph.append(current)
            pending.extend((current.__cause__, current.__context__, *cls._group_members(exception=current)))
        return graph

    @classmethod
    def _groups_members_first(cls, *, graph: list[BaseException]) -> list[BaseException]:
        """The exception groups of `graph`, each after the groups among its members, since a group is built from its members' copies."""
        ordered: list[BaseException] = []
        placed: set[int] = set()
        for root in graph:
            if not isinstance(root, BaseExceptionGroup):
                continue
            expanding: set[int] = set()
            stack: list[tuple[BaseException, bool]] = [(root, False)]
            while stack:
                group, members_placed = stack.pop()
                if id(group) in placed:
                    continue
                if members_placed:
                    placed.add(id(group))
                    ordered.append(group)
                    continue
                if id(group) in expanding:
                    continue
                expanding.add(id(group))
                stack.append((group, True))
                stack.extend(
                    (member, False)
                    for member in cls._group_members(exception=group)
                    if cls._group_members(exception=member) and id(member) not in placed
                )
        return ordered

    @classmethod
    def _group_members(cls, *, exception: BaseException) -> tuple[BaseException, ...]:
        """The members PostHog expands out of an exception group, or nothing for any other error."""
        if isinstance(exception, BaseExceptionGroup):
            return cast("BaseExceptionGroup[BaseException]", exception).exceptions
        return ()

    @classmethod
    def _redacted_stand_in(cls, *, exception: BaseException) -> BaseException:
        """Build a same-class stand-in for `exception` whose message is the privacy notice.

        `__new__` without arguments and without `__init__` is the point: the
        instance comes out with an empty `__dict__`, so none of the error's own
        attributes, the concepts it was comparing, the file it was reading, the
        input a model refused, travel with it. What goes out is the class name,
        the notice and the traceback. A class that cannot be built that way, a
        pydantic `ValidationError` for one, stands as a plain `Exception` naming
        it, and never with its own text.
        """
        exception_type = type(exception)
        try:
            stand_in = exception_type.__new__(exception_type)
            stand_in.args = (cls.PRIVACY_NOTICE,)
            stand_in_attributes = getattr(stand_in, "__dict__", None)
            if stand_in_attributes:
                stand_in_attributes.clear()
        except Exception:  # ruff: ignore[blind-except]
            # (2) any class's `__new__` runs here, whose exception surface cannot be enumerated; its name still travels.
            return Exception(f"{exception_type.__name__}: {cls.PRIVACY_NOTICE}")
        return stand_in

    @classmethod
    def _redacted_group_stand_in(cls, *, group: BaseException, members: list[BaseException]) -> BaseException:
        """Build a same-class stand-in for an exception group, over its members' stand-ins, whose message is the privacy notice.

        A group keeps its members because PostHog expands them, each its own
        error with its own frames. Its notes are left behind, as every
        attribute is.
        """
        group_type = type(group)
        if not members:
            return Exception(f"{group_type.__name__}: {cls.PRIVACY_NOTICE}")
        try:
            stand_in = group_type.__new__(group_type, cls.PRIVACY_NOTICE, members)
            stand_in_attributes = getattr(stand_in, "__dict__", None)
            if stand_in_attributes:
                stand_in_attributes.clear()
        except Exception:  # ruff: ignore[blind-except]
            # (2) a group subclass's own `__new__` runs here, whose exception surface cannot be enumerated.
            return BaseExceptionGroup(f"{group_type.__name__}: {cls.PRIVACY_NOTICE}", members)
        return stand_in

    @override
    def setup(self, *, integration_mode: IntegrationMode):
        pass

    @override
    def teardown(self):
        # The error trackers, the posthog one over this manager's client included, were reset by the boot before this
        # teardown, so no exception is captured during shutdown.

        # First, shutdown the TracerProvider to flush all pending spans
        # This MUST happen before PostHog shutdown, otherwise spans won't be exported
        if self._tracer_provider:
            try:
                log.verbose("The OpenTelemetry tracer provider is shutting down and flushing its pending spans")
                self._tracer_provider.shutdown()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Suppress any shutdown errors to avoid cascading failures
                log.debug("The OpenTelemetry tracer provider could not be shut down", fields=error_fields(exc=exc))

        # Then shutdown the PostHog client
        if self.custom_posthog_client:
            try:
                self.custom_posthog_client.shutdown()
            except Exception as exc:  # ruff: ignore[blind-except]
                # Suppress any shutdown errors to avoid cascading failures
                log.debug("The custom PostHog client could not be shut down", fields=error_fields(exc=exc))

        # Clear singleton instance
        TelemetryManagerAbstract.clear_instance()

    @override
    def track_event(
        self,
        event_name: EventName,
        *,
        properties: dict[EventProperty, Any] | None = None,
        run_metadata: "RunMetadata | None" = None,
    ):
        # We copy the incoming properties to avoid modifying the original dictionary
        # and to convert the keys to str
        # and to remove the properties that are in the redact list
        tracked_properties: dict[str, Any]
        if properties:
            tracked_properties = {key: value for key, value in properties.items() if key not in self.telemetry_config.redact_properties}
        else:
            tracked_properties = {}

        caller_identity = self.resolve_event_caller_identity(run_metadata=run_metadata)

        # Track to PostHog based on the user's posthog.mode
        match self.telemetry_config.custom_posthog.mode:
            case PostHogMode.ANONYMOUS:
                # The operator chose not to identify people, and that choice covers
                # their users too: no run identity is applied and no groups are sent.
                self._capture_custom_event(event_name, properties=tracked_properties, identity=TelemetryIdentity.make_anonymous())
            case PostHogMode.IDENTIFIED:
                if not self.telemetry_config.custom_posthog.user_id:
                    log.warning(
                        "An event with no user id to identify it was tracked as anonymous",
                        fields={"event_name": event_name},
                    )
                    self._capture_custom_event(event_name, properties=tracked_properties, identity=TelemetryIdentity.make_anonymous())
                else:
                    self._capture_custom_event(
                        event_name,
                        properties=tracked_properties,
                        identity=TelemetryIdentity.make_from_caller_identity(
                            caller_identity=caller_identity,
                            fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                            run_identity_policy=RunIdentityPolicy.DIRECT,
                        ),
                    )
            case PostHogMode.OFF:
                # Custom telemetry is off: the event goes nowhere.
                pass

    @classmethod
    def resolve_event_caller_identity(cls, *, run_metadata: "RunMetadata | None") -> CallerIdentity | None:
        """The caller an event is attributed to: its run's, else the one in scope, else nobody.

        The run an emitter hands over is the most specific fact there is, so it
        wins. An emitter with no run in hand — the validation sweep, which is not
        a run — is still working for somebody when a host or a pipe run opened a
        caller scope around it, and reads that caller rather than falling back to
        the stream's constant. Only an event emitted outside every scope, such as
        a CLI command, belongs to nobody.
        """
        if run_metadata is not None:
            return CallerIdentity.make_from_run_metadata(run_metadata=run_metadata)
        return get_current_caller_identity()

    def _capture_custom_event(self, event_name: str, *, properties: dict[str, Any], identity: TelemetryIdentity):
        """Capture one event on the operator's stream, under the identity resolved for it.

        Captures a COPY of the properties, because the anonymous branch below
        stamps `$process_person_profile` onto the one it sends, and the caller's
        dict must not carry that mark away with it.
        """
        if not self.custom_posthog_client:
            log.error("An event could not be tracked to custom telemetry, which has no PostHog client")
            return
        capture_properties = dict(properties)
        if identity.distinct_id:
            self.custom_posthog_client.capture(
                event_name,
                distinct_id=identity.distinct_id,
                properties=capture_properties,
                groups=identity.groups or None,
            )
        else:
            capture_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
            self.custom_posthog_client.capture(event_name, properties=capture_properties)

    @override
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """Context manager that uses PostHog's new_context when telemetry is enabled."""
        with new_context():
            yield

    @override
    def is_custom_portkey_logging_enabled(self, *, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if not is_debug and self.telemetry_config.custom_portkey.force_debug_enabled:
            log.verbose("Portkey logging (debug mode) is forced on by custom_portkey.force_debug_enabled in the telemetry configuration")
            is_debug = True
        if is_debug and is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            # DEBUG rather than WARNING: honouring DO_NOT_TRACK over every other setting is the documented rule, not a
            # degradation, and this runs on every Portkey call.
            log.debug(
                "Portkey logging (debug mode) is off because DO_NOT_TRACK takes precedence",
                fields={"env_var": OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY},
            )
            is_debug = False
        return is_debug

    @override
    def is_custom_portkey_tracing_enabled(self) -> bool:
        if self.telemetry_config.custom_portkey.force_tracing_enabled and not is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            # DEBUG, not INFO: this is asked on every Portkey inference call, and a setting the user chose is no milestone.
            log.debug("Portkey tracing is forced on by custom_portkey.force_tracing_enabled in the telemetry configuration")
            return True
        else:
            return False

    @override
    def get_otel_tracer(self) -> OTelTracer | None:
        return self._otel_tracer

    @property
    @override
    def capture_content_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.content

    @property
    @override
    def capture_pipe_codes_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.pipe_codes

    @property
    @override
    def capture_output_class_name_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.output_class_names

    @property
    @override
    def capture_content_max_length(self) -> int | None:
        return self.telemetry_config.custom_posthog.tracing.capture.content_max_length

    @property
    @override
    def is_langfuse_enabled(self) -> bool:
        return self.telemetry_config.langfuse.enabled

    @override
    def handle_trace_start(self, *, trace_name: str, trace_name_redacted: str, trace_id: int, run_metadata: "RunMetadata | None" = None) -> None:
        """Hook to do something when a trace starts.

        Emits a trace start event to establish the trace name in PostHog.
        We send a minimal $ai_span event with the trace_name as the span name.
        This event is sent directly (not via OTel spans) to ensure it arrives
        before any batched pipe spans, establishing the correct trace name.

        Args:
            trace_name: Full trace name with pipe code.
            trace_name_redacted: Redacted trace name without pipe code, used when pipe codes are not captured.
            trace_id: The trace ID.
            run_metadata: The run this trace belongs to. Carries the identity the
                event is attributed to, resolved exactly as every pipe span under
                the same trace will be, so the trace's first event and its spans
                land on the same person. None reads the caller in scope, and
                only with none in scope leaves the stream's fallback.
        """
        caller_identity = self.resolve_event_caller_identity(run_metadata=run_metadata)

        # Send to PostHog if configured (uses full trace name based on user's capture settings)
        if self.custom_posthog_client and self.telemetry_config.custom_posthog.tracing.enabled:
            # Use full or redacted trace name based on user's capture_pipe_codes setting
            custom_trace_name = trace_name if self.telemetry_config.custom_posthog.tracing.capture.pipe_codes else trace_name_redacted
            custom_properties: dict[str, Any] = {
                PostHogAttr.TRACE_ID: f"{trace_id:032x}",
                PostHogAttr.SPAN_NAME: custom_trace_name,
                PostHogAttr.TRACE_NAME: custom_trace_name,
            }
            if run_metadata is not None:
                custom_properties[EventProperty.PIPELINE_RUN_ID] = run_metadata.pipeline_run_id
            custom_identity = TelemetryIdentity.make_from_caller_identity(
                caller_identity=caller_identity,
                fallback_distinct_id=self.telemetry_config.custom_posthog.user_id,
                run_identity_policy=RunIdentityPolicy.make_for_operator_stream(posthog_mode=self.telemetry_config.custom_posthog.mode),
            )
            if custom_identity.distinct_id:
                self.custom_posthog_client.capture(
                    distinct_id=custom_identity.distinct_id,
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                    groups=custom_identity.groups or None,
                )
            else:
                custom_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
                self.custom_posthog_client.capture(
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                )
