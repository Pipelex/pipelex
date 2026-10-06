"""The `backends.toml` tables and per-backend files the backend library's unit tests load."""

ABSENT_VAR = "PIPELEX_TEST_ABSENT_VAR_FOR_CREDENTIALS"
LITERAL_FIELD_VAR = "PIPELEX_TEST_VAR_IN_A_LITERAL_FIELD"


class BackendLibraryTomls:
    BACKENDS_TOML = """
[acme]
enabled = true
api_key = "sk-not-a-real-key"
"""

    BACKENDS_TOML_WITH_MISSING_CREDENTIAL = f"""
[acme]
enabled = true
api_key = "${{{ABSENT_VAR}}}"
"""

    MODEL_SPECS_TOML = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
"""

    MODEL_SPECS_TOML_WITH_UNKNOWN_DEFAULT = """
[defaults]
model_type = "llm"
sdk = "openai_responses"
a_field_we_removed = "openai"

["acme-one"]
model_id = "acme-one"
"""

    MODEL_SPECS_TOML_WITH_UNKNOWN_PER_MODEL_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
max_tokns = 4096
"""

    MODEL_SPECS_TOML_WITH_NEAR_MISS_PER_MODEL_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
max-tokens = 4096
"""

    MODEL_SPECS_TOML_WITH_HEADER_KEY = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-portkey-provider = "@openai"
"""

    MODEL_SPECS_TOML_WITH_NON_STRING_HEADER_VALUE = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-foo = 3
"""

    MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_NAME = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
"x-foo bar" = "value"
"""

    MODEL_SPECS_TOML_WITH_ILLEGAL_HEADER_VALUE = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
x-foo = "trailing "
"""

    MODEL_SPECS_TOML_WITH_MISSING_CREDENTIAL = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "${{{ABSENT_VAR}}}"
"""

    MODEL_SPECS_TOML_WITH_MISSING_FALLBACK_PATTERN = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "${{env:{ABSENT_VAR}_A|env:{ABSENT_VAR}_B}}"
"""

    BACKENDS_TOML_WITH_EVERY_CREDENTIAL_SHAPE = """
[acme]
enabled = true
endpoint = "${ACME_ENDPOINT}"
api_key = "${secret:ACME_API_KEY}"
region = "${env:ACME_REGION|secret:ACME_REGION}"
debug = true
listed_constraints = ["temperature_unsupported"]
valued_constraints = { fixed_temperature = 1 }
"""

    BACKENDS_TOML_WITH_A_LITERAL_ENDPOINT = """
[acme]
enabled = true
endpoint = "https://api.acme.example/v1"
api_key = "${ACME_API_KEY}"
"""

    BACKENDS_TOML_WITH_NO_CREDENTIAL = """
[acme]
enabled = true
endpoint = "http://localhost:11434/v1"
"""

    VERTEXAI_BACKENDS_TOML = """
[vertexai]
enabled = true
gcp_project_id = "a-project"
gcp_location = "us-central1"
gcp_credentials_file_path = "/nowhere/service-account.json"
"""

    VERTEXAI_MODEL_SPECS_TOML = """
[defaults]
model_type = "llm"
sdk = "openai"

["gemini-one"]
model_id = "google/gemini-one"
"""

    MODEL_SPECS_TOML_WITH_A_TEMPLATED_MODEL_TYPE = f"""
[defaults]
model_type = "${{{LITERAL_FIELD_VAR}}}"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
"""

    MODEL_SPECS_TOML_WITH_A_TEMPLATED_THINKING_MODE = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "acme-one"
thinking_mode = "${{env:{LITERAL_FIELD_VAR}}}"
"""

    BACKENDS_TOML_WITH_A_TEMPLATED_CONSTRAINT = f"""
[acme]
enabled = true
api_key = "sk-not-a-real-key"
listed_constraints = ["${{{LITERAL_FIELD_VAR}}}"]
"""

    BACKENDS_TOML_WITH_AN_UNKNOWN_PREFIX = """
[acme]
enabled = true
api_key = "${secrte:ACME_API_KEY}"
"""

    MODEL_SPECS_TOML_WITH_AN_UNKNOWN_PREFIX = """
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
model_id = "${secrte:ACME_MODEL}"
"""
