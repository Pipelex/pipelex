from typing import Annotated

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class NetworkConfig(ConfigModel):
    """Outbound network posture of the runtime.

    ``is_fetch_ssrf_guard_enabled`` decides whether fetching the bytes behind a URL a value carries
    (a document, an image, a provider's generated file) goes through the SSRF guard, which refuses
    every destination and redirect hop that is not a globally routable address. It is on by default;
    a self-hosted deployment that reads documents from an intranet host, or whose only way out is an
    HTTP proxy, turns it off. Webhook delivery is guarded regardless of this switch.

    ``max_fetch_bytes`` is the most bytes such a fetch reads, counted after the body is decoded: an
    uncompressed response declaring a larger ``Content-Length`` is refused before its body is read,
    and one that keeps coming is cut off once it passes the cap. A caller with a limit of its own,
    such as the document conversion's ``max_source_bytes``, passes it, and the smaller of the two
    applies: a caller can tighten the cap, never loosen it.
    """

    is_fetch_ssrf_guard_enabled: bool
    max_fetch_bytes: Annotated[int, Field(ge=1)]
