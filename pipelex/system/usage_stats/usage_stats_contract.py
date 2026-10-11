"""The facts of the usage-statistics contract that pipelex sends by, mirrored from its schema.

The contract is `conformance/specs/usage-statistics.md`, whose machine-readable source is
`usage-statistics.json`. pipelex vendors that file byte for byte at
`tests/data/usage_stats/usage-statistics.json`, and the tests under `tests/unit/pipelex/system/usage_stats/`
check every constant and enum here against it, so a change to the contract that these do not follow fails
the suite rather than reaching PostHog's gate, which drops what it does not know.

This module imports nothing but the standard library: the detached sender (`usage_stats_sender`) reads it
in a process started with `python -I -m`, which should load as little as it can.
"""

from enum import StrEnum
from typing import Final

SCHEMA_VERSION = 1

#: The reporting tool's name, the `tool` property and the name of its spool directory.
TOOL_NAME: Final = "pipelex"

CAPTURE_HOST = "https://eu.i.posthog.com"
BATCH_PATH = "/batch/"
#: The project's ingestion token. It is public by design: it can only write events, and the gate decides what is kept.
PROJECT_TOKEN = "phc_uQjSVbzNPJxA8bHxfevn7NMzB6PbC6aJQRB6ka6MxT7a"

PERSON_PROFILE_PROPERTY = "$process_person_profile"

NOTICE_VERSION = 1
NOTICE_DETAILS_URL = "https://docs.pipelex.com/latest/setup/usage-statistics/"
NOTICE_DISABLE_COMMAND = "pipelex usage-stats disable"
NOTICE_TEXT_TEMPLATE = (
    "Pipelex collects anonymous usage statistics: counts of commands, runs, pipe types, models and tokens, and the country your IP "
    "address maps to; the address itself is never stored. It never collects your methods, prompts, inputs, outputs, file names or "
    "pipe names. To turn it off, run `{disable_command}` or set DO_NOT_TRACK=1. Details: {details_url}"
)


def render_notice() -> str:
    """The notice as pipelex prints it."""
    return NOTICE_TEXT_TEMPLATE.format(disable_command=NOTICE_DISABLE_COMMAND, details_url=NOTICE_DETAILS_URL)


class UsageStatsEnvVar(StrEnum):
    """The environment variables the contract names."""

    DO_NOT_TRACK = "DO_NOT_TRACK"
    TOOL_SWITCH = "PIPELEX_USAGE_STATS"
    DEBUG = "PIPELEX_USAGE_STATS_DEBUG"
    ENDPOINT_OVERRIDE = "PIPELEX_USAGE_STATS_ENDPOINT"
    HOST = "PIPELEX_USAGE_STATS_HOST"


#: Values of `DO_NOT_TRACK` and `PIPELEX_USAGE_STATS_DEBUG` that have no effect, trimmed and lowercased; unset has none either.
FALSY_VALUES: frozenset[str] = frozenset({"", "0", "false"})
#: Values of `PIPELEX_USAGE_STATS` that turn statistics off. Any value in neither set turns them off too, failing closed.
TOOL_SWITCH_OFF_VALUES: frozenset[str] = frozenset({"0", "false", "no", "off"})
#: Values of `PIPELEX_USAGE_STATS` that have no effect, since a variable cannot turn statistics on over another switch.
TOOL_SWITCH_NO_EFFECT_VALUES: frozenset[str] = frozenset({"", "1", "true", "yes", "on"})
#: Values of the legacy `DISABLE_TELEMETRY` in `~/.mthds/config` that mean statistics are off.
LEGACY_DISABLE_ON_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "on"})

#: The shared state directory, under the home directory.
STATE_DIR_PARTS: tuple[str, ...] = (".mthds", "usage-stats")
ID_FILE_NAME = "id"
DISABLED_FILE_NAME = "disabled"
LEGACY_MIGRATED_FILE_NAME = "legacy-migrated"
NOTICE_FILE_PREFIX = "notice-v"
INTERNAL_FILE_NAME = "internal"
SPOOL_DIR_NAME = "spool"
#: Today's `mthds` CLI configuration, under the home directory, and the key its opt-out is stored under.
LEGACY_CONFIG_PARTS: tuple[str, ...] = (".mthds", "config")
LEGACY_KEY = "DISABLE_TELEMETRY"
#: Every tool's spool directory, which `disable`, `reset-id` and the legacy migration empty.
SPOOL_TOOLS: tuple[str, ...] = ("pipelex", "plxt", "vscode-pipelex", "mthds")

SPOOL_VERSION = 1
SPOOL_MAX_FILES_PER_TOOL = 100
SPOOL_MAX_AGE_DAYS = 30
SPOOL_STALE_CLAIM_MINUTES = 10
SPOOL_STALE_TEMP_MINUTES = 60
#: A temporary identifier file older than this is a crashed writer's leftover, which any tool may delete.
ID_STALE_TEMP_MINUTES = 60

BUDGET_CLI_IN_PROCESS_MS = 1000
BUDGET_PYTHON_EXIT_FLUSH_MS = 250
BUDGET_SHUTDOWN_FLUSH_MS = 2000
BUDGET_DETACHED_SENDER_MS = 10000
BUDGET_BACKGROUND_POST_DELAY_MS = 10000

#: Responses after which a sender deletes what it posted, since a resend would be refused again.
PERMANENT_REFUSAL_STATUSES: frozenset[int] = frozenset({400, 401, 403, 413})

CI_VARIABLES: tuple[str, ...] = (
    "CI",
    "CONTINUOUS_INTEGRATION",
    "BUILD_NUMBER",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "CIRCLECI",
    "TRAVIS",
    "BUILDKITE",
    "TF_BUILD",
    "JENKINS_URL",
    "TEAMCITY_VERSION",
    "BITBUCKET_BUILD_NUMBER",
    "CODEBUILD_BUILD_ID",
    "DRONE",
    "APPVEYOR",
    "SEMAPHORE",
    "WOODPECKER",
)
CONTAINER_MARKER_FILES: tuple[str, ...] = ("/.dockerenv", "/run/.containerenv")
CONTAINER_MARKER_VARIABLES: tuple[str, ...] = ("container", "KUBERNETES_SERVICE_HOST")
CONTAINER_CGROUP_FILE = "/proc/1/cgroup"
CONTAINER_CGROUP_WORDS: tuple[str, ...] = ("docker", "kubepods", "containerd", "lxc")

#: The project setting's table and key in a project's `.pipelex/pipelex.toml`, and in pipelex's packaged configuration.
SETTING_TABLE = "usage_stats"
SETTING_KEY = "enabled"


class UsageStatsOffBy(StrEnum):
    """The switches pipelex honours, by their `off_by` token, in the contract's order."""

    DO_NOT_TRACK = "do_not_track"
    TOOL_VARIABLE = "tool_variable"
    MACHINE_CHOICE = "machine_choice"
    LEGACY_MTHDS_CHOICE = "legacy_mthds_choice"
    PROJECT_SETTING = "project_setting"
    PACKAGED_DEFAULT = "packaged_default"
    INTEGRATION_MODE = "integration_mode"
    INVALID_ENDPOINT_OVERRIDE = "invalid_endpoint_override"


class UsageStatsEventName(StrEnum):
    """The events pipelex sends."""

    RUN_COMPLETED = "run_completed"
    MODEL_USED = "model_used"
    COMMAND_COMPLETED = "command_completed"
    METHOD_VALIDATED = "method_validated"
    CODE_GENERATED = "code_generated"


class UsageStatsSurface(StrEnum):
    """Which entry point of pipelex sent an event."""

    PIPELEX = "pipelex"
    PIPELEX_AGENT = "pipelex-agent"
    API = "api"
    PYTHON = "python"


class UsageStatsIntegration(StrEnum):
    """The pipelex runtime's integration mode, as the `integration` property names it."""

    CLI = "cli"
    PYTHON = "python"
    FASTAPI = "fastapi"
    DOCKER = "docker"
    MCP = "mcp"
    N8N = "n8n"
    CI = "ci"


class UsageStatsHost(StrEnum):
    """The program of ours that embeds or spawns pipelex, when one declares itself."""

    COCODE = "cocode"
    MTHDS_AGENT = "mthds-agent"
    OTHER = "other"


class UsageStatsOs(StrEnum):
    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"
    OTHER = "other"


class UsageStatsArch(StrEnum):
    X86_64 = "x86_64"
    ARM64 = "arm64"
    OTHER = "other"


class UsageStatsOutcome(StrEnum):
    """How a command or a run ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_failed(self) -> bool:
        """Whether the event carries an error domain, which only a failure does."""
        match self:
            case UsageStatsOutcome.FAILED:
                return True
            case UsageStatsOutcome.SUCCEEDED | UsageStatsOutcome.CANCELLED:
                return False


class UsageStatsErrorDomain(StrEnum):
    """Who can fix a failure: the runtime's own error domains, `other` when it cannot say."""

    INPUT = "input"
    CONFIG = "config"
    RUNTIME = "runtime"
    OTHER = "other"


class UsageStatsMethodSource(StrEnum):
    """Where a run's method came from, by kind only."""

    LOCAL_BUNDLE = "local_bundle"
    INLINE_SOURCE = "inline_source"
    INSTALLED_METHOD = "installed_method"
    PUBLISHED_ADDRESS = "published_address"
    CATALOG_ID = "catalog_id"
    OTHER = "other"


class UsageStatsValidationOutcome(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    FAILED = "failed"


class UsageStatsCodegenOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class UsageStatsCodegenArtifact(StrEnum):
    TYPES = "types"
    INPUTS = "inputs"
    STRUCTURES = "structures"
    OTHER = "other"

    @property
    def has_target(self) -> bool:
        """Whether a `code_generated` of this artifact names a target: only typed artifacts are generated for one."""
        match self:
            case UsageStatsCodegenArtifact.TYPES:
                return True
            case UsageStatsCodegenArtifact.INPUTS | UsageStatsCodegenArtifact.STRUCTURES | UsageStatsCodegenArtifact.OTHER:
                return False


class UsageStatsCodegenTarget(StrEnum):
    PYTHON_STRUCTURES = "python-structures"
    PYTHON_PYDANTIC = "python-pydantic"
    TS_ZOD = "ts-zod"
    OTHER = "other"


class UsageStatsProvider(StrEnum):
    """The backend a model was called through: one pipelex ships, one our own plugins add, or `custom`."""

    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    BEDROCK = "bedrock"
    BLACKBOXAI = "blackboxai"
    FAL = "fal"
    GOOGLE = "google"
    GROQ = "groq"
    HUGGINGFACE = "huggingface"
    INTERNAL = "internal"
    LINKUP = "linkup"
    MINIMAX = "minimax"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    PORTKEY = "portkey"
    SCALEWAY = "scaleway"
    TYPESAFE = "typesafe"
    VERTEXAI = "vertexai"
    XAI = "xai"
    PIPELEX_MANIFOLD = "pipelex_manifold"
    CUSTOM = "custom"

    @property
    def is_custom(self) -> bool:
        match self:
            case UsageStatsProvider.CUSTOM:
                return True
            case (
                UsageStatsProvider.ANTHROPIC
                | UsageStatsProvider.AZURE_OPENAI
                | UsageStatsProvider.BEDROCK
                | UsageStatsProvider.BLACKBOXAI
                | UsageStatsProvider.FAL
                | UsageStatsProvider.GOOGLE
                | UsageStatsProvider.GROQ
                | UsageStatsProvider.HUGGINGFACE
                | UsageStatsProvider.INTERNAL
                | UsageStatsProvider.LINKUP
                | UsageStatsProvider.MINIMAX
                | UsageStatsProvider.MISTRAL
                | UsageStatsProvider.OLLAMA
                | UsageStatsProvider.OPENAI
                | UsageStatsProvider.OPENROUTER
                | UsageStatsProvider.PORTKEY
                | UsageStatsProvider.SCALEWAY
                | UsageStatsProvider.TYPESAFE
                | UsageStatsProvider.VERTEXAI
                | UsageStatsProvider.XAI
                | UsageStatsProvider.PIPELEX_MANIFOLD
            ):
                return False

    @property
    def serves_every_shipped_table(self) -> bool:
        """Whether the backend serves the models of every backend table pipelex ships, as Manifold, the hosted gateway, does."""
        match self:
            case UsageStatsProvider.PIPELEX_MANIFOLD:
                return True
            case (
                UsageStatsProvider.CUSTOM
                | UsageStatsProvider.ANTHROPIC
                | UsageStatsProvider.AZURE_OPENAI
                | UsageStatsProvider.BEDROCK
                | UsageStatsProvider.BLACKBOXAI
                | UsageStatsProvider.FAL
                | UsageStatsProvider.GOOGLE
                | UsageStatsProvider.GROQ
                | UsageStatsProvider.HUGGINGFACE
                | UsageStatsProvider.INTERNAL
                | UsageStatsProvider.LINKUP
                | UsageStatsProvider.MINIMAX
                | UsageStatsProvider.MISTRAL
                | UsageStatsProvider.OLLAMA
                | UsageStatsProvider.OPENAI
                | UsageStatsProvider.OPENROUTER
                | UsageStatsProvider.PORTKEY
                | UsageStatsProvider.SCALEWAY
                | UsageStatsProvider.TYPESAFE
                | UsageStatsProvider.VERTEXAI
                | UsageStatsProvider.XAI
            ):
                return False


#: The model name a custom backend, or a model the release does not ship, is sent as.
OTHER_MODEL = "other"

#: The `command` values of the `pipelex` CLI, by their path in its command tree.
PIPELEX_COMMANDS: frozenset[str] = frozenset(
    {
        "init",
        "login",
        "doctor",
        "update",
        "migrate",
        "build inputs bundle",
        "build inputs method",
        "build inputs pipe",
        "build output bundle",
        "build output method",
        "build output pipe",
        "build structures",
        "validate",
        "validate bundle",
        "validate method",
        "validate pipe",
        "fix bundle",
        "resolve",
        "codegen types",
        "codegen inputs",
        "codegen check",
        "run bundle",
        "run method",
        "run pipe",
        "graph render",
        "show config",
        "show pipe",
        "show models",
        "show backends",
        "which",
        "plugins list",
        "other",
    }
)
#: The `command` values of the `pipelex-agent` CLI.
PIPELEX_AGENT_COMMANDS: frozenset[str] = frozenset(
    {
        "init",
        "run bundle",
        "run method",
        "run pipe",
        "validate",
        "validate bundle",
        "validate method",
        "validate pipe",
        "fix bundle",
        "fmt",
        "lint",
        "inputs bundle",
        "inputs method",
        "inputs pipe",
        "codegen types",
        "codegen inputs",
        "codegen check",
        "models",
        "check-model",
        "migrate",
        "doctor",
        "other",
    }
)
#: The `command` a command the schema does not list yet sends.
OTHER_COMMAND = "other"

#: The patterns of the contract the emitter's own values must match, in Python's `re.fullmatch`.
RELEASE_VERSION_PATTERN = r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}([.-]?(a|b|rc|alpha|beta|dev|post|insider)[.]?[0-9]{0,4})?$"
INSTALLATION_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
MODEL_HANDLE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,95}$"
