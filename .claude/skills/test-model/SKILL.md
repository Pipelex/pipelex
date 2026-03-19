---
name: test-model
description: >
  Test an AI model on a specific backend using the Pipelex inference test
  infrastructure. Handles test profile creation, fixture regeneration, and
  running the right test class for the model type (LLM, image gen, extract,
  search). Use when the user says "test model X", "test gpt-5.4 on openai",
  "test model on gateway", "run inference test for model", "try model X on
  backend Y", "verify model X works", or any variation of running inference
  tests against a specific model on a specific backend. Also use when the user
  mentions testing a model after adding it, or wants to verify a model works
  end-to-end with real API calls.
---

# Test a Model on a Backend

This skill runs inference tests for a specific model on a specific backend. It
creates a temporary test profile, regenerates fixtures, runs the tests, and
cleans up.

## Step 1: Identify the model and backend

Gather from the user (or infer from context):

| Field | Description | Example |
|-------|-------------|---------|
| **Model name** | The model handle as it appears in backend TOMLs | `gpt-5.2-codex` |
| **Backend** | Which backend to test on | `pipelex_gateway` |
| **Model type** | `llm`, `img_gen`, `extract`, or `search` | `llm` |

### How to determine the model type

If the user doesn't specify the model type, look it up:

1. Check which collection the model belongs to in
   `.pipelex-dev/test_profiles.toml` — models under `[collections.llm]` are LLM,
   under `[collections.img_gen]` are image gen, etc.
2. Or check the backend TOML at `.pipelex/inference/backends/<backend>.toml` —
   the `[defaults]` section usually has `model_type`.

### How to determine the backend

If the user says a backend name, use it directly. Common shorthand mappings:

| User says | Backend name |
|-----------|-------------|
| "gateway" | `pipelex_gateway` |
| "openai" | `openai` |
| "azure" | `azure_openai` |
| "anthropic" | `anthropic` |
| "bedrock" | `bedrock` |
| "google" | `google` |
| "vertex" | `vertexai` |
| "mistral" | `mistral` |
| "groq" | `groq` |

### Verify the model exists on the target backend

Before creating a test profile, confirm the model is actually configured on the
target backend. For most backends, check the TOML file:

```
.pipelex/inference/backends/<backend_name>.toml
```

For **gateway** (`pipelex_gateway`), the model list is fetched remotely — you
cannot verify locally. Proceed and let the test tell you if the model isn't
available.

## Step 2: Create a temporary test profile

Edit `.pipelex-dev/test_profiles_override.toml` (this file is gitignored) to add
a temporary profile. Choose a descriptive profile name.

The profile must specify:
- `backends` — a single-element list with the target backend
- The right model list field for the model type — only one should be non-empty

```toml
[profiles.test_<model_slug>_<backend_slug>]
description = "Test <model> on <backend>"
backends = ["<backend_name>"]
llm_models = []
img_gen_models = []
extract_models = []
search_models = []
```

Set the appropriate model list based on model type:
- **LLM**: `llm_models = ["<model_name>"]`
- **Image gen**: `img_gen_models = ["<model_name>"]`
- **Extract**: `extract_models = ["<model_name>"]`
- **Search**: `search_models = ["<model_name>"]`

### Handling existing profiles in the override file

The override file may already contain profiles from previous testing sessions.
Don't remove existing profiles — just add or update the one you need.

## Step 3: Run tests

Run the appropriate test class. **No need to call `make rtm` separately** — all
inference test targets automatically regenerate fixtures when `PROF=` is passed
on the command line.

```bash
make test-inference-with-prints PROF=<profile_name> TEST=<TestClass>
```

Map model type to test class:

| Model type | Test class | Make shortcut |
|------------|-----------|---------------|
| LLM | `TestLLMInference` | `make test-inference-with-prints` |
| Image gen | `TestImageGeneration` | `make test-inference-with-prints` |
| Extract | `TestExtract` | `make test-inference-with-prints` |
| Search | `TestSearch` | `make test-inference-with-prints` |

All use `make test-inference-with-prints` since all these test classes are marked
with the `inference` pytest marker.

For LLM models specifically, there are additional test classes you can run for
deeper coverage (only if the user wants thorough testing):

| Test class | What it tests |
|------------|--------------|
| `TestLLMGenText` | Text generation variants |
| `TestLLMGenObject` | Structured object generation |
| `TestLLMVision` | Vision / image input |
| `TestLLMReasoning` | Reasoning / thinking mode |
| `TestLLMDocument` | Document processing |

## Step 4: Interpret results

- **Tests pass**: The model works on this backend. Report success.
- **Tests fail**: Read the error output carefully.
  - Authentication errors → API key not configured for this backend
  - Model not found → model ID is wrong or model isn't available on this backend
  - Capability errors (e.g., vision not supported) → expected skips, not failures
  - Timeout / rate limit → transient, suggest retrying

## Step 5: Clean up (optional)

Ask the user if they want the temporary profile removed from
`test_profiles_override.toml`. If yes, remove it. If no, leave it — the file is
gitignored.
