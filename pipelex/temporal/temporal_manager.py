from typing import ClassVar, Optional

import shortuuid
from temporalio.client import Client as TemporalClient

from pipelex import log
from pipelex.system.runtime import RunMode, runtime_manager
from pipelex.temporal.config_temporal import TemporalServerConfig
from pipelex.temporal.temporal_connect import connect_to_temporal, connect_to_temporal_selected_server, connect_to_temporal_server
from pipelex.types import StrEnum


class TemporalWorkerEnvironment(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class TemporalManager:
    _shared_instance: ClassVar[Optional["TemporalManager"]] = None

    def __init__(self, session_id: str) -> None:
        if TemporalManager._shared_instance is not None:
            msg = "TemporalManager is a singleton. Use get_instance() to access it."
            raise RuntimeError(msg)
        super().__init__()
        self.session_id = session_id
        self.temporal_client: TemporalClient | None = None
        TemporalManager._shared_instance = self

    @classmethod
    def get_instance(cls) -> "TemporalManager":
        if cls._shared_instance is None:
            msg = "Shared instance is not set. You must call TemporalManager.setup() once."
            raise RuntimeError(msg)
        return cls._shared_instance

    @classmethod
    def setup(cls, session_id: str) -> None:
        cls._shared_instance = cls(session_id=session_id)
        log.debug(f"TemporalManager setup done, session_id={session_id}")

    @classmethod
    def teardown(cls) -> None:
        cls._shared_instance = None

    async def connect_temporal(
        self,
        temporal_client: TemporalClient | None = None,
        temporal_server_config: TemporalServerConfig | None = None,
        temporal_selected_server: str | None = None,
    ) -> TemporalClient:
        """One remark first: this method is async only because Temporal's Client.connect() method is async.

        This method is only passing your settings or using defaults from pipelex.temporal's config.
        To init the temporal client, it will use one of the provided arguments if available, in the following order:
        - temporal_client
        - temporal_server_config
        - temporal_selected_server
        ... otherwise it will use the default connection set by temporal's config.
        """
        # select temporal client based on the available arguments
        the_temporal_client: TemporalClient
        if temporal_client:
            log.dev("Connecting temporal using provided Temporal client")
            the_temporal_client = temporal_client
        elif temporal_server_config:
            log.dev(f"Connecting temporal using provided Temporal server config: {temporal_server_config.description}")
            the_temporal_client = await connect_to_temporal_server(
                server_config=temporal_server_config,
            )
        elif temporal_selected_server:
            log.dev(f"Connecting temporal using selected Temporal server: {temporal_selected_server}")
            the_temporal_client = await connect_to_temporal_selected_server(
                selected_server_config=temporal_selected_server,
            )
        else:
            log.dev("Connecting temporal using default Temporal client")
            # use automatic default connection
            the_temporal_client = await connect_to_temporal()
        self.temporal_client = the_temporal_client
        log.debug(f"Temporal client connected, session_id={self.session_id}")
        return the_temporal_client

    async def get_temporal_client(self, should_auto_connect: bool) -> TemporalClient:
        if self.temporal_client is not None:
            return self.temporal_client
        elif should_auto_connect:
            return await self.connect_temporal()
        else:
            msg = "Temporal client not connected. Enable should_auto_connect or call TemporalManager.connect_temporal() first."
            raise RuntimeError(msg)

    def make_top_workflow_id(self, base_id: str) -> str:
        prefix: str
        match runtime_manager.run_mode:
            case RunMode.UNIT_TEST:
                prefix = "ut-"
            case RunMode.NORMAL:
                prefix = ""
            case RunMode.CI_TEST:
                prefix = "ci-"
            case RunMode.CODEX_CLOUD:
                prefix = "cc-"
            case RunMode.CODEX_CLOUD_TEST:
                prefix = "cct-"
        session_part = self.session_id[:5]
        random_part = shortuuid.uuid()[:5]
        return f"{prefix}{session_part}-{random_part}-{base_id}"


def get_temporal_manager() -> TemporalManager:
    return TemporalManager.get_instance()


async def get_temporal_client(should_auto_connect: bool) -> TemporalClient:
    return await get_temporal_manager().get_temporal_client(should_auto_connect=should_auto_connect)
