# Demoted public surfaces — release-wave cross-repo sweep handoff

The subject-grant review demoted every positional first parameter that failed the grant rubric to keyword-only (see `docs/contribute/keyword-only-arguments.md`). No backward compatibility: any external consumer calling these surfaces positionally — or subclassing them with positional signatures — breaks when the release ships. This is the inventory for the release-gated cross-repo sweep; the consumers to check are `pipelex-api`, `pipelex-worker`, the private `pipelex-temporal` plugin, `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows`, and any starter/template code.

## Runtime / execution surfaces

- `pipelex.core.pipes.pipe_abstract.PipeAbstract` run family (`run_pipe`, `live_run_pipe`, `dry_run_pipe`, `validate_before_run`, `validate_after_run`, `needed_inputs`) — `job_metadata` / `visited_pipes` now keyword-only; external code subclassing or invoking pipes positionally breaks.
- `pipelex.runtime_bridge.bootstrap.ensure_pipelex_booted` (`config_overrides`) — runtime_bridge is consumed by pipelex-api / pipelex-worker; positional callers break.
- `pipelex.pipeline.pipeline_run_setup.pipeline_run_setup` (`execution_config`) and `pipelex.pipeline.pipeline_manager_abstract.add_new_pipeline` (`pipe_code`).
- `pipelex.libraries.library_manager_abstract.LibraryManagerAbstract` load family (`load_libraries`, `load_from_blueprints`, `load_from_crate`, …) — `library_id` now keyword-only.
- `pipelex.libraries.concept.concept_library_abstract.ConceptLibraryAbstract.is_compatible` / `ConceptLibrary.is_compatible` (`tested_concept`).
- `pipelex.graph.graph_tracer_protocol.GraphTracerProtocol.setup` (`graph_id`) + `GraphTracer.setup` / `GraphTracerNoOp.setup` — external tracer implementations must match.

## Content / rendering surfaces

- `pipelex.core.stuffs.stuff_content.StuffContent.rendered_for_prompt` / `rendered_for_template_async` (`text_format`) and `pretty_print_content` (`title`) — public content API; positional `TextFormat` callers break.
- `pipelex.tools.jinja2.text_format_renderable.TextFormatRenderable.rendered_for_template_async` (`text_format`) — `@runtime_checkable` protocol; external implementers and positional callers break.
- `pipelex.tools.jinja2.image_renderable.ImageRenderable.render_with_images` (`registry`) — protocol + all content-class implementations.
- `pipelex.cogt.image.prompt_image_factory.PromptImageFactory.make_prompt_image` (`uri`) and `pipelex.cogt.document.prompt_document_factory.PromptDocumentFactory.make_prompt_document` (`uri`) — public content factories; positional-`uri` callers (cookbook, cocode, app) break.

## Model / backend / reporting surfaces

- `pipelex.cogt.models.model_manager_abstract.ModelManagerAbstract.setup` + `ModelManager.setup` (`secrets_provider`) and `pipelex.cogt.model_backends.backend_library.InferenceBackendLibrary.load` (`secrets_provider`).
- `pipelex.cogt.llm.llm_setting.LLMSettingChoices.make_completed_with_defaults` (`for_text`) and `pipelex.cogt.model_routing.routing_profile.RoutingProfile.get_backend_match_for_model` (`enabled_backends`).
- `pipelex.reporting` protocol methods `set_event_log` / `clear_event_log` (`context_key`) — external `ReportingProtocol` implementations must match.
- `pipelex.system.telemetry.*.is_custom_portkey_logging_enabled` / `is_pipelex_gateway_portkey_logging_enabled` (`is_debug_configured`).
- `pipelex.plugins.anthropic.anthropic_factory.AnthropicFactory.calculate_safe_max_tokens_for_timeout` (`timeout_seconds`).
- `pipelex.tools.aws.aws_config.AwsConfig.get_aws_access_keys_with_method` (`api_key_method`).

## Builder / CLI-adjacent importable surfaces

- `pipelex.builder.operations` entry points `build_inputs_for_pipe` (`pipe_code`), `list_models` (`categories`), `validate_all` (`library_dirs`) — agent-CLI/MCP plumbing, but importable.
- `pipelex.cli.installed_methods.discover_installed_methods` (`include_global`) and `pipelex.cli.commands.init.config_files.init_config` (`reset`).
- `pipelex.hub.PipelexHub.set_dry_run_forced` (`is_forced`).

## Tools helpers (literal sweep)

- `pipelex.tools.misc.string_utils.pluralize` / `count_with_noun` (`count`).
- `pipelex.tools.log.log.Log.set_level_by_int` (`level_int`) and `pipelex.tools.log.log_levels.LogLevel.from_int` (`logging_level`).
- `pipelex.tools.misc.pretty.PrettyPrinter.pretty_width` (`width`).
- `pipelex.errors.error_pages_generator.generate_error_pages` (`output_dir`) — dev tooling, listed for completeness.

CLI-internal helpers (doctor/show/update/validate `*_cmd` delegates, console UI builders, plugin-internal `list_*_models` / discovery register helpers, gateway `_call_relay`) were also demoted but are not part of the importable public API — they live in the commit diffs, not here.
