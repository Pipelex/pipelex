"""Factory for building a :class:`StoragePayloadCodec` from the Pipelex config."""

from __future__ import annotations

from pipelex.config import get_config
from pipelex.temporal.codec.storage_payload_codec import StoragePayloadCodec
from pipelex.tools.storage.storage_provider_factory import make_storage_provider_from_config


def make_codec_from_config() -> StoragePayloadCodec:
    """Build a :class:`StoragePayloadCodec` from the current Pipelex config.

    Returns:
        A fully configured codec backed by the storage provider specified in
        ``temporal.payload_codec_config``.
    """
    payload_codec_config = get_config().temporal.payload_codec_config
    storage_provider = make_storage_provider_from_config(payload_codec_config.storage_provider_config)
    return StoragePayloadCodec(
        storage_provider=storage_provider,
        size_threshold=payload_codec_config.size_threshold,
        storage_prefix=payload_codec_config.storage_prefix,
    )
