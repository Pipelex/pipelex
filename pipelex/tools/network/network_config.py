from pipelex.system.configuration.config_model import ConfigModel


class NetworkConfig(ConfigModel):
    """Outbound network posture of the runtime.

    ``is_fetch_ssrf_guard_enabled`` decides whether fetching the bytes behind a URL a value carries
    (a document, an image, a provider's generated file) goes through the SSRF guard, which refuses
    every destination and redirect hop that is not a globally routable address. It is on by default;
    a self-hosted deployment that reads documents from an intranet host, or whose only way out is an
    HTTP proxy, turns it off. Webhook delivery is guarded regardless of this switch.
    """

    is_fetch_ssrf_guard_enabled: bool
