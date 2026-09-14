# Execution Graph Visualization

Full transparency into pipeline execution with interactive visualizations.

## Overview

Every pipeline execution can be visualized as an interactive graph, giving developers full transparency into what happened, in what order, and with what data at each step. Running with the `--graph` flag writes the graph outputs (graph spec JSON, Mermaid chart, interactive HTML) to the run's output directory. To render a saved graph spec and open it in your browser, use `pipelex graph render <graph.json> --open`.

## Interactive HTML Visualization

Inspect any pipeline execution with a local ReactFlow-based interface. Nodes represent pipes, edges show data flow, and clicking any node reveals the data at that stage. The visualization supports zooming, panning, and collapsing nested controllers.

## Mermaid Chart Export

Render pipeline diagrams anywhere that supports Mermaid: VS Code, GitHub, web applications, and documentation. Mermaid charts provide a static, embeddable view of the pipeline structure.

## Step-by-Step Data Inspection

View the actual data at each execution stage:

- **JSON** — Raw structured data
- **HTML preview** — Rendered content
- **Images** — Generated or extracted images
- **Embedded PDFs** — Document content

## CLI Flags

- `--graph` — Generate an execution graph after running a pipeline
- `--graph-full-data` — Include full data payloads in the graph
- `--graph-no-data` — Generate a structural graph without data

<!-- path verified: resolves to docs/images/flow-chart-example.png -->
![Execution Graph Example](../images/flow-chart-example.png){ width="400" }
