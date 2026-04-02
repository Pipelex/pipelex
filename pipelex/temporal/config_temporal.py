from datetime import timedelta
from typing import TYPE_CHECKING, Literal, Union

from pydantic import Field, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.temporal.exceptions import TemporalConfigError
from pipelex.types import Self, StrEnum

if TYPE_CHECKING:
    from temporalio.common import RetryPolicy


class SecretMethod(StrEnum):
    NONE = "none"
    ENV_VAR = "env_var"
    SECRET_PROVIDER = "secret_provider"


class TemporalServerConfig(ConfigModel):
    """Configuration model for Temporal server settings."""

    description: str
    target_host: str
    namespace: str
    api_key_method: SecretMethod = Field(strict=False)
    api_key_id: str

    @property
    def full_description(self) -> str:
        """Generate a full description of the Temporal server configuration.

        Returns:
            str: A detailed description including non-default target host and namespace.
        """
        desc = self.description
        if self.target_host != "localhost:7233":
            desc += f", target host: {self.target_host}"
        if self.namespace != "default":
            desc += f", namespace: {self.namespace}"
        return desc


class TemporalLogConfig(ConfigModel):
    """Configuration model for Temporal logging settings."""

    is_workflow_info_on_message: bool
    is_workflow_info_on_extra: bool
    is_full_workflow_info_on_extra: bool
    is_activity_info_on_message: bool
    is_activity_info_on_extra: bool
    is_full_activity_info_on_extra: bool
    is_formatter_enabled: bool
    is_prefix_enabled: bool
    managed_loggers: list[str]


class TemporalTasksConfig(ConfigModel):
    required_tasks_packs: list[str]
    required_workflows: list[str]
    required_activities: list[str]


class TemporalConfig(ConfigModel):
    """Configuration model for overall Temporal settings."""

    temporal_server_configs: dict[str, TemporalServerConfig]
    selected_server: str
    temporal_log_config: TemporalLogConfig
    temporal_tasks_config: TemporalTasksConfig

    @model_validator(mode="after")
    def validate_selected_server(self) -> Self:
        """Validate that the selected server exists in the server configurations.

        Raises:
            TemporalConfigError: If the selected server is not found in the configurations.

        Returns:
            Self: The validated instance.
        """
        if self.selected_server not in self.temporal_server_configs:
            msg = f"Selected server '{self.selected_server}' not found in temporal_server_configs"
            raise TemporalConfigError(msg)
        return self


class RetryPolicyConfig(ConfigModel):
    """Configuration model for retry policy settings."""

    initial_interval: timedelta = Field(strict=False)
    backoff_coefficient: float
    maximum_interval: Union[timedelta, Literal["unlimited"]]
    maximum_attempts: Union[int, Literal["unlimited"]]
    non_retryable_error_types: list[str]

    def make_retry_policy(self) -> "RetryPolicy":
        """Create a RetryPolicy instance based on the configuration.

        Returns:
            RetryPolicy: A configured RetryPolicy object.
        """
        from temporalio.common import RetryPolicy as _RetryPolicy  # noqa: PLC0415

        maximum_attempts: int
        if self.maximum_attempts == "unlimited":
            # This is according to the Temporal SDK's documentation
            maximum_attempts = 0
        else:
            maximum_attempts = self.maximum_attempts

        maximum_interval: timedelta | None
        # this test is in two steps because timedelta's are actually read from the config as strings
        if isinstance(self.maximum_interval, str) and self.maximum_interval == "unlimited":
            maximum_interval = None
        else:
            maximum_interval = self.maximum_interval

        return _RetryPolicy(
            initial_interval=self.initial_interval,
            backoff_coefficient=self.backoff_coefficient,
            maximum_interval=maximum_interval,
            maximum_attempts=maximum_attempts,
            non_retryable_error_types=self.non_retryable_error_types,
        )


# class PipelexWorkflowsConfig(ConfigModel):
#     """Configuration model for workflow settings."""

#     jinja2_activity_timeout: timedelta = Field(strict=False)
#     jinja2_retry_policy_config: RetryPolicyConfig

#     @property
#     def jinja2_retry_policy(self) -> RetryPolicy:
#         """
#         Create a RetryPolicy for LLM generation based on the configuration.

#         Returns:
#             RetryPolicy: A configured RetryPolicy object for LLM generation.
#         """
#         return self.jinja2_retry_policy_config.make_retry_policy()


class WorkerConfig(ConfigModel):
    """Configuration model for workflow execution settings."""

    task_queue: str
    workflow_execution_timeout: timedelta = Field(strict=False)
    run_timeout: timedelta | None = Field(default=None, strict=False)
    task_timeout: timedelta | None = Field(default=None, strict=False)
    start_delay: timedelta | None = Field(default=None, strict=False)
    rpc_timeout: timedelta | None = Field(default=None, strict=False)
    retry_policy_config: RetryPolicyConfig

    @property
    def retry_policy(self) -> "RetryPolicy":
        """Create a RetryPolicy based on the configuration.

        Returns:
            RetryPolicy: A configured RetryPolicy object.
        """
        return self.retry_policy_config.make_retry_policy()


class StorageProviderType(StrEnum):
    LOCAL = "local"


class PayloadCodecConfig(ConfigModel):
    """Configuration for the storage-based payload codec that offloads large payloads."""

    is_enabled: bool
    size_threshold: int
    storage_prefix: str
    storage_provider: StorageProviderType = Field(strict=False)
    storage_root_path: str


class Temporal(ConfigModel):
    """Main configuration model for Temporal."""

    is_enabled: bool
    temporal_config: TemporalConfig
    worker_config: WorkerConfig
    payload_codec_config: PayloadCodecConfig
