# Suspects — package `plugins`

Reviewed: 49 Section A + 15 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/plugins/gateway/gateway_completions_factory.py:138` — `GatewayCompletionsFactory.make_extract_output_from_response` — `def make_extract_output_from_response(cls, inference_model: InferenceModelSpec, *, response: GenericResponse) -> ExtractOutput` — The function name is "from_response", strongly signalling that `response` is the primary operand (the thing being processed/extracted from). `inference_model` is used only as a lookup key to select which extraction sub-method to call (via `GatewayExtractProtocol.make_from_model_handle`). Swapping `inference_model` and `response` so the response is the subject, or making both keyword-only, would match the semantics. Suggested fix: make fully keyword-only `def make_extract_output_from_response(cls, *, inference_model: InferenceModelSpec, response: GenericResponse)`.

## Medium / low confidence

- `pipelex/plugins/anthropic/anthropic_factory.py:244` — `AnthropicFactory.make_nb_tokens_by_category_from_nb` — `def make_nb_tokens_by_category_from_nb(nb_input: int, *, nb_output: int) -> NbTokensByCategoryDict` — Symmetric directional pair (`nb_input` / `nb_output`); neither operand is more "the subject" than the other. Splitting them across the `*` barrier is arbitrary and reads oddly. Suggested fix: make fully keyword-only `def make_nb_tokens_by_category_from_nb(*, nb_input: int, nb_output: int)`. Note: no external call sites found in the codebase, so risk is low.

- `pipelex/plugins/mistral/mistral_factory.py:365` — `MistralFactory.make_mistral_document_url_chunk_from_uri` — `async def make_mistral_document_url_chunk_from_uri(cls, mistral_client: Mistral, *, uri: str) -> DocumentURLChunkTypedDict` — The function name ends in "from_uri", indicating `uri` is the primary operand. `mistral_client` is a dependency/tool passed to sub-operations (local file upload). The docstring itself labels it "required for local file uploads", framing it as an auxiliary dependency rather than the semantic subject. Suggested fix: make fully keyword-only `def make_mistral_document_url_chunk_from_uri(cls, *, mistral_client: Mistral, uri: str)`.

- `pipelex/plugins/plugin_sdk_registry.py:22` — `PluginSdkRegistry.set_sdk_instance` — `def set_sdk_instance(self, plugin: Plugin, *, sdk_instance: Any) -> Any` — The registry is keyed by `plugin.sdk_handle`; `plugin` acts as an index/key, while `sdk_instance` is the actual object being stored. "Set X instance" semantically implies `sdk_instance` is the subject. Call sites already pass both as keyword args (`set_sdk_instance(plugin=plugin, sdk_instance=...)`). Suggested fix: make fully keyword-only `def set_sdk_instance(self, *, plugin: Plugin, sdk_instance: Any)`.
