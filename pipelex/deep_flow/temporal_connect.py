from typing import Mapping

from temporalio.client import Client as TemporalClient

from pipelex import log
from pipelex.config import get_config
from pipelex.deep_flow.config_deep_flow import SecretMethod, TemporalConfigError, TemporalServerConfig
from pipelex.deep_flow.exceptions import TemporalServerError
from pipelex.deep_flow.temporal_data_converter import data_converter
from pipelex.hub import get_secret
from pipelex.system.environment import get_required_env


async def connect_to_temporal_server(server_config: TemporalServerConfig, name: str | None = None) -> TemporalClient:
    """Connect to Temporal using the provided server config."""
    api_key: str | None
    match server_config.api_key_method:
        case SecretMethod.NONE:
            api_key = None
        case SecretMethod.ENV_VAR:
            if api_key_id := server_config.api_key_id:
                api_key = get_required_env(api_key_id)
            else:
                msg = "api_key_id is required for api_key_method=ENV_VAR"
                raise TemporalConfigError(msg)
        case SecretMethod.SECRET_PROVIDER:
            if api_key_id := server_config.api_key_id:
                api_key = get_secret(secret_id=api_key_id)
            else:
                msg = "api_key_id is required for api_key_method=SECRET_PROVIDER"
                raise TemporalConfigError(msg)

    tls: bool
    rpc_metadata: Mapping[str, str]
    if api_key:
        rpc_metadata = {"temporal-namespace": server_config.namespace}
        tls = True
    else:
        rpc_metadata = {}
        tls = False

    log.info(f"Connecting to Temporal server: {server_config.full_description}")
    log.info(
        f"""Establishing connection to Temporal...
        - Selected Server Config : {name}
        - Target Host            : {server_config.target_host}
        - Namespace              : {server_config.namespace}
        - TLS Enabled            : {"Yes" if tls else "No"}
        - API Key                : {"Provided" if api_key else "Not Provided"}
        - RPC Metadata           : {rpc_metadata or "None"}
    """,
    )

    try:
        temporal_client: TemporalClient = await TemporalClient.connect(
            target_host=server_config.target_host,
            namespace=server_config.namespace,
            rpc_metadata=rpc_metadata,
            api_key=api_key,
            data_converter=data_converter,
            tls=tls,
        )
    except RuntimeError as exc:
        msg = f"Failed to connect to Temporal server using config: {server_config.full_description}\nError: {exc}"
        raise TemporalServerError(msg) from exc
    return temporal_client


async def connect_to_temporal_selected_server(
    selected_server_config: str,
) -> TemporalClient:
    """Connect to Temporal using the server selected by argument."""
    temporal_config = get_config().deep_flow.temporal_config
    log.dev(f"Using Temporal server config named: '{selected_server_config}'")
    server_config = temporal_config.temporal_server_configs.get(selected_server_config)
    if not server_config:
        msg = f"Server config not found for selected server: '{selected_server_config}'"
        raise TemporalConfigError(msg)
    temporal_client = await connect_to_temporal_server(server_config=server_config, name=selected_server_config)
    log.info(f"Connected to Temporal server: '{selected_server_config}' = {server_config.full_description}")
    return temporal_client


async def connect_to_temporal() -> TemporalClient:
    """Connect to Temporal using the server selected from the config."""
    temporal_config = get_config().deep_flow.temporal_config
    return await connect_to_temporal_selected_server(
        selected_server_config=temporal_config.selected_server,
    )
