---
title: "Under the Hood"
description: "Technical deep-dives into Pipelex internals — architecture, execution tracing, image handling, reasoning controls, and more."
---

# Under the Hood

Welcome to the technical deep-dives of Pipelex. This section is for contributors, curious developers, AI agents, and anyone doing due diligence on how Pipelex works internally.

## What You'll Find Here

- **Architecture Overview** - The two-layer design and how components fit together
- **Build-time Elaboration** - How shorthand directives like `structuring_method = "preliminary_text"` are rewritten into concrete pipe trees before any pipe runs
- **Execution Graph Tracing** - How pipeline executions are captured as graphs for visualization
- **Image Handling in LLM Prompts** - How images flow from inputs to LLM calls
- **Reasoning Controls** - How reasoning effort/budget flows to each provider's SDK
- **StuffArtefact & Image Rendering** - How template access and image extraction work
- **Test Profile Configuration** - How to configure which models are used in tests
- **Dry Run Mock Generation** - How mock objects satisfy field validation constraints
- **Init CLI Flows** - How `pipelex init` sets up the configuration directory
- **Distributed Content Generation** - How dynamic classes and large payloads cross Temporal boundaries
- **Technical Design Decisions** - Why we chose X over Y
- **Module Deep-Dives** - Detailed explanations of specific subsystems

!!! info "Not Required for Using Pipelex"
    You don't need to read this section to use Pipelex effectively. The [Home](../index.md) section covers everything you need to build methods.

!!! tip "Looking for Temporal deployment and operations?"
    For running Pipelex on Temporal — cluster setup, workers, task-queue routing, and dashboard observability — see the user-facing [Distributed Execution with Temporal](../distributed-execution/index.md) guide. The pages below cover the runtime mechanics that make distributed execution work under the hood.

---

## Start Exploring

- [:material-sitemap: Architecture Overview](./architecture-overview.md){ .md-button .md-button--primary }
- [:material-source-branch: Build-time Elaboration](./build-time-elaboration.md){ .md-button }
- [:material-graph: Execution Graph Tracing](./execution-graph-tracing.md){ .md-button }
- [:material-image-multiple: Image Handling in LLM Prompts](./image-handling-in-llm-prompts.md){ .md-button }
- [:material-brain: Reasoning Controls](./reasoning-controls.md){ .md-button }
- [:material-code-braces: StuffArtefact & Image Rendering](./stuffartefact-and-image-rendering.md){ .md-button }
- [:material-test-tube: Test Profile Configuration](./test-profile-configuration.md){ .md-button }
- [:material-flask-outline: Dry Run Mock Generation](./dry-run-mock-generation.md){ .md-button }
- [:material-console: Init CLI Flows](./init-cli-flows.md){ .md-button }
- [:material-pipe: Pipe Routing & Execution](./pipe-routing-and-execution.md){ .md-button }
- [:material-cloud-sync: Temporal Integration](./temporal-integration.md){ .md-button }
- [:material-swap-horizontal: Distributed Content Generation](./distributed-content-generation.md){ .md-button }

