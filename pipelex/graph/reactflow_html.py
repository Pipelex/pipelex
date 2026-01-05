"""ReactFlow HTML generator for ViewSpec rendering.

This module provides functions to generate standalone HTML files with embedded
ReactFlow viewers that can render ViewSpec graphs interactively.
"""

import json

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.viewspec import ViewSpec
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync

# ReactFlow HTML template with embedded viewer
REACTFLOW_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    {% if use_cdn %}
    <!-- React and ReactDOM from CDN -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <!-- ReactFlow from CDN (v11 - using reactflow package for UMD support) -->
    <script src="https://unpkg.com/reactflow@11.11.4/dist/umd/index.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/reactflow@11.11.4/dist/style.css">
    <!-- Dagre for layout -->
    <script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            height: 100vh;
            overflow: hidden;
        }
        #root {
            width: 100%;
            height: 100%;
        }
        .react-flow-container {
            width: 100%;
            height: 100%;
        }
        .inspector-panel {
            position: fixed;
            top: 10px;
            right: 10px;
            width: 300px;
            max-height: 80vh;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            padding: 16px;
            overflow-y: auto;
            z-index: 10;
            display: none;
        }
        .inspector-panel.visible {
            display: block;
        }
        .inspector-header {
            font-weight: 600;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #eee;
        }
        .inspector-close {
            float: right;
            cursor: pointer;
            color: #999;
            font-size: 20px;
            line-height: 1;
        }
        .inspector-close:hover {
            color: #333;
        }
        .inspector-content {
            font-size: 13px;
            line-height: 1.5;
        }
        .inspector-section {
            margin-bottom: 16px;
        }
        .inspector-section-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: #666;
        }
        .inspector-value {
            word-break: break-word;
        }
        .inspector-pre {
            background: #f5f5f5;
            padding: 8px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
            overflow-x: auto;
        }
    </style>
    {% else %}
    <!-- Inline dependencies would go here for offline mode -->
    <!-- For now, we'll still use CDN but this is where bundled JS would be -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/reactflow@11.11.4/dist/umd/index.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/reactflow@11.11.4/dist/style.css">
    <script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
    {% endif %}
</head>
<body>
    <div id="root"></div>
    <div id="inspector" class="inspector-panel">
        <div class="inspector-header">
            <span id="inspector-title">Node Details</span>
            <span class="inspector-close" onclick="closeInspector()">&times;</span>
        </div>
        <div id="inspector-content" class="inspector-content"></div>
    </div>

    <!-- Embedded ViewSpec -->
    <script type="application/json" id="pipelex-viewspec">{{ viewspec_json }}</script>
    {% if graphspec_json %}
    <!-- Embedded GraphSpec (optional, for inspector) -->
    <script type="application/json" id="pipelex-graphspec">{{ graphspec_json }}</script>
    {% endif %}

    <script>
        // Parse embedded ViewSpec
        const viewspecElement = document.getElementById('pipelex-viewspec');
        const viewspec = JSON.parse(viewspecElement.textContent);

        // Parse GraphSpec if present
        const graphspecElement = document.getElementById('pipelex-graphspec');
        const graphspec = graphspecElement ? JSON.parse(graphspecElement.textContent) : null;

        // ReactFlow setup
        const { React, ReactDOM } = window;
        // reactflow UMD exposes window.ReactFlowRenderer
        const ReactFlowLib = window.ReactFlowRenderer || window.ReactFlow || {};
        const { ReactFlow, useNodesState, useEdgesState, Background, Controls, MiniMap } = ReactFlowLib;

        // Dagre layout function
        function getLayoutedElements(nodes, edges, direction = 'TB') {
            const g = new dagre.graphlib.Graph();
            g.setDefaultEdgeLabel(() => ({}));
            g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

            nodes.forEach((node) => {
                g.setNode(node.id, { width: 150, height: 50 });
            });

            edges.forEach((edge) => {
                g.setEdge(edge.source, edge.target);
            });

            dagre.layout(g);

            const layoutedNodes = nodes.map((node) => {
                const nodeWithPosition = g.node(node.id);
                return {
                    ...node,
                    position: {
                        x: nodeWithPosition.x - 75,
                        y: nodeWithPosition.y - 25,
                    },
                };
            });

            return { nodes: layoutedNodes, edges };
        }

        // Main React component
        function GraphViewer() {
            // Convert ViewSpec to ReactFlow format
            const initialNodes = viewspec.nodes.map(node => ({
                id: node.id,
                type: node.type || 'default',
                data: {
                    label: node.label,
                    ...node.inspector,
                },
                position: node.position || { x: 0, y: 0 },
                style: {
                    background: node.ui?.classes?.includes('failed') ? '#fee' :
                               node.ui?.classes?.includes('succeeded') ? '#efe' : '#fff',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    padding: '10px',
                },
                parentId: node.parent_id,
            }));

            const initialEdges = viewspec.edges.map(edge => ({
                id: edge.id,
                source: edge.source,
                target: edge.target,
                type: edge.type || 'default',
                animated: edge.animated || false,
                label: edge.label,
            }));

            // Apply layout if positions are missing
            const needsLayout = initialNodes.some(n => !n.position || (n.position.x === 0 && n.position.y === 0));
            const layouted = needsLayout
                ? getLayoutedElements(initialNodes, initialEdges, viewspec.layout.direction)
                : { nodes: initialNodes, edges: initialEdges };

            const [nodes, setNodes, onNodesChange] = useNodesState(layouted.nodes);
            const [edges, setEdges, onEdgesChange] = useEdgesState(layouted.edges);

            const onNodeClick = (event, node) => {
                const inspector = document.getElementById('inspector');
                const inspectorContent = document.getElementById('inspector-content');
                const inspectorTitle = document.getElementById('inspector-title');

                inspectorTitle.textContent = node.data.label || node.id;

                let html = '';
                if (node.data.pipe_code) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Pipe Code</div>
                        <div class="inspector-value">${node.data.pipe_code}</div>
                    </div>`;
                }
                if (node.data.pipe_type) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Pipe Type</div>
                        <div class="inspector-value">${node.data.pipe_type}</div>
                    </div>`;
                }
                if (node.data.timing) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Timing</div>
                        <div class="inspector-pre">${JSON.stringify(node.data.timing, null, 2)}</div>
                    </div>`;
                }
                if (node.data.io_preview) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">I/O</div>
                        <div class="inspector-pre">${JSON.stringify(node.data.io_preview, null, 2)}</div>
                    </div>`;
                }
                if (node.data.error) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Error</div>
                        <div class="inspector-pre">${JSON.stringify(node.data.error, null, 2)}</div>
                    </div>`;
                }

                inspectorContent.innerHTML = html || '<div>No additional information</div>';
                inspector.classList.add('visible');
            };

            if (!ReactFlow) {
                return React.createElement('div', { style: { padding: '20px' } },
                    React.createElement('p', null, 'Loading ReactFlow...')
                );
            }

            return React.createElement('div', { className: 'react-flow-container' },
                React.createElement(ReactFlow, {
                    nodes: nodes,
                    edges: edges,
                    onNodesChange: onNodesChange,
                    onEdgesChange: onEdgesChange,
                    onNodeClick: onNodeClick,
                    fitView: true,
                },
                    Background ? React.createElement(Background, {}) : null,
                    Controls ? React.createElement(Controls, {}) : null,
                    MiniMap ? React.createElement(MiniMap, {}) : null
                )
            );
        }

        // Render the app
        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(React.createElement(GraphViewer));

        // Close inspector function
        function closeInspector() {
            document.getElementById('inspector').classList.remove('visible');
        }

        // Close inspector on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeInspector();
            }
        });
    </script>
</body>
</html>
"""


def generate_reactflow_html(
    viewspec: ViewSpec,
    *,
    graphspec: GraphSpec | None = None,
    use_cdn: bool = True,
    title: str = "Pipelex Graph",
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer.

    Args:
        viewspec: The ViewSpec to embed and render.
        graphspec: Optional GraphSpec to embed (for inspector details).
        use_cdn: If True, load ReactFlow from CDN. If False, use inline bundles (not yet implemented).
        title: The page title.

    Returns:
        Complete HTML page as a string with embedded ReactFlow viewer.
    """
    # Serialize ViewSpec to JSON
    viewspec_json = json.dumps(viewspec.model_dump(mode="json"), indent=2)

    # Serialize GraphSpec to JSON if provided
    graphspec_json: str | None = None
    if graphspec:
        graphspec_json = json.dumps(graphspec.model_dump(mode="json"), indent=2)

    # Render template
    return render_jinja2_sync(
        template_source=REACTFLOW_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "use_cdn": use_cdn,
        },
    )


async def generate_reactflow_html_async(
    viewspec: ViewSpec,
    *,
    graphspec: GraphSpec | None = None,
    use_cdn: bool = True,
    title: str = "Pipelex Graph",
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer (async version).

    Use this when inside an async event loop.

    Args:
        viewspec: The ViewSpec to embed and render.
        graphspec: Optional GraphSpec to embed (for inspector details).
        use_cdn: If True, load ReactFlow from CDN. If False, use inline bundles (not yet implemented).
        title: The page title.

    Returns:
        Complete HTML page as a string with embedded ReactFlow viewer.
    """
    # Serialize ViewSpec to JSON
    viewspec_json = json.dumps(viewspec.model_dump(mode="json"), indent=2)

    # Serialize GraphSpec to JSON if provided
    graphspec_json: str | None = None
    if graphspec:
        graphspec_json = json.dumps(graphspec.model_dump(mode="json"), indent=2)

    # Render template
    return await render_jinja2_async(
        template_source=REACTFLOW_HTML_TEMPLATE,
        template_category=TemplateCategory.HTML,
        temlating_context={
            "title": title,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "use_cdn": use_cdn,
        },
    )
