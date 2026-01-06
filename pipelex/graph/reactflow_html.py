"""ReactFlow HTML generator for ViewSpec rendering.

This module provides functions to generate standalone HTML files with embedded
ReactFlow viewers that can render ViewSpec graphs interactively.
"""

import json

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.graph.graphspec import GraphSpec
from pipelex.graph.viewspec import ViewSpec
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async, render_jinja2_sync
from pipelex.urls import URLs

# ReactFlow HTML template with embedded viewer - Dataflow View
# This template renders a dataflow graph with pipe nodes and stuff (data) nodes,
REACTFLOW_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <!-- React and ReactDOM from CDN -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <!-- ReactFlow from CDN (v11 - using reactflow package for UMD support) -->
    <script src="https://unpkg.com/reactflow@11.11.4/dist/umd/index.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/reactflow@11.11.4/dist/style.css">
    <!-- Dagre for layout -->
    <script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --color-bg: #0f172a;
            --color-surface: #1e293b;
            --color-surface-hover: #334155;
            --color-border: #334155;
            --color-text: #f1f5f9;
            --color-text-muted: #94a3b8;
            --color-text-dim: #64748b;
            --color-accent: #3b82f6;
            --color-accent-hover: #60a5fa;
            --color-success: #10b981;
            --color-success-bg: rgba(16, 185, 129, 0.15);
            --color-error: #ef4444;
            --color-error-bg: rgba(239, 68, 68, 0.15);
            --color-warning: #f59e0b;
            --color-stuff: #f59e0b;
            --color-stuff-bg: rgba(245, 158, 11, 0.15);
            --color-stuff-border: #d97706;
            --color-pipe: #3b82f6;
            --color-pipe-bg: rgba(59, 130, 246, 0.1);
            --color-pipe-failed: #ef4444;
            --color-pipe-failed-bg: rgba(239, 68, 68, 0.15);
            --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            --font-mono: 'JetBrains Mono', 'Monaco', 'Menlo', monospace;
            --radius-sm: 4px;
            --radius-md: 8px;
            --radius-lg: 12px;
            --radius-pill: 999px;
            --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: var(--font-sans);
            height: 100vh;
            overflow: hidden;
            background: var(--color-bg);
            color: var(--color-text);
        }
        #app-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 20px;
            background: var(--color-surface);
            border-bottom: 1px solid var(--color-border);
            z-index: 100;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .header-logo {
            height: 28px;
            width: auto;
        }
        .header-title {
            font-size: 14px;
            color: var(--color-text-muted);
            font-weight: 500;
        }
        .header-stats {
            display: flex;
            gap: 16px;
        }
        .stat-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--color-text-muted);
        }
        .stat-value {
            font-weight: 600;
            color: var(--color-text);
        }
        .stat-icon {
            width: 16px;
            height: 16px;
            opacity: 0.7;
        }
        #root {
            flex: 1;
            width: 100%;
            overflow: hidden;
        }
        .react-flow-container {
            width: 100%;
            height: 100%;
            background: var(--color-bg);
        }
        .react-flow__node {
            font-family: var(--font-sans);
        }
        .react-flow__background {
            background: var(--color-bg) !important;
        }
        .react-flow__controls {
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
        }
        .react-flow__controls-button {
            background: var(--color-surface);
            border-bottom: 1px solid var(--color-border);
            fill: var(--color-text-muted);
        }
        .react-flow__controls-button:hover {
            background: var(--color-surface-hover);
        }
        .react-flow__minimap {
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
            box-shadow: var(--shadow-md);
        }
        .react-flow__edge-path {
            stroke-width: 2;
        }
        .react-flow__edge-text {
            font-size: 11px;
            fill: var(--color-text-muted);
        }
        .react-flow__edge-textbg {
            fill: var(--color-bg);
        }

        /* Inspector Panel */
        .inspector-panel {
            position: fixed;
            top: 70px;
            right: 16px;
            width: 400px;
            max-height: calc(100vh - 90px);
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-lg);
            overflow: hidden;
            z-index: 1000;
            display: none;
        }
        .inspector-panel.visible {
            display: flex;
            flex-direction: column;
        }
        .inspector-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            background: linear-gradient(135deg, var(--color-accent), var(--color-stuff));
            color: white;
        }
        .inspector-header.stuff {
            background: linear-gradient(135deg, var(--color-stuff), var(--color-stuff-border));
        }
        .inspector-header.pipe {
            background: linear-gradient(135deg, var(--color-pipe), var(--color-accent));
        }
        .inspector-title {
            font-size: 15px;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .inspector-subtitle {
            font-size: 12px;
            opacity: 0.85;
            margin-top: 2px;
        }
        .inspector-close {
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            background: rgba(255,255,255,0.2);
            border-radius: var(--radius-sm);
            font-size: 18px;
            line-height: 1;
            transition: background 0.15s;
        }
        .inspector-close:hover {
            background: rgba(255,255,255,0.3);
        }
        .inspector-content {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }
        .inspector-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }
        .inspector-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 500;
            border-radius: 999px;
        }
        .inspector-badge.success {
            background: var(--color-success-bg);
            color: var(--color-success);
        }
        .inspector-badge.error {
            background: var(--color-error-bg);
            color: var(--color-error);
        }
        .inspector-badge.neutral {
            background: var(--color-surface-hover);
            color: var(--color-text-muted);
        }
        .inspector-badge.stuff {
            background: var(--color-stuff-bg);
            color: var(--color-stuff);
        }
        .inspector-section {
            margin-bottom: 16px;
        }
        .inspector-section:last-child {
            margin-bottom: 0;
        }
        .inspector-section-title {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--color-text-dim);
            margin-bottom: 8px;
        }
        .inspector-value {
            font-size: 14px;
            color: var(--color-text);
            word-break: break-word;
        }
        .inspector-value.pipe-code {
            font-family: var(--font-mono);
            color: var(--color-accent);
        }
        .inspector-pre {
            background: var(--color-bg);
            border: 1px solid var(--color-border);
            padding: 12px;
            border-radius: var(--radius-md);
            font-family: var(--font-mono);
            font-size: 12px;
            line-height: 1.5;
            color: var(--color-text-muted);
            overflow-x: auto;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }
        /* No-wrap variant for Rich-formatted ASCII tables (Pretty/Text tab) */
        .inspector-pre.nowrap {
            white-space: pre;
            word-break: normal;
            line-height: 0.8;
            -webkit-overflow-scrolling: touch;
        }
        .inspector-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid var(--color-border);
        }
        .inspector-row:last-child {
            border-bottom: none;
        }
        .inspector-row-label {
            color: var(--color-text-dim);
            font-size: 13px;
        }
        .inspector-row-value {
            color: var(--color-text);
            font-size: 13px;
            font-weight: 500;
        }

        /* Format tabs for stuff data */
        .format-tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 12px;
        }
        .format-tab {
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            background: var(--color-surface-hover);
            color: var(--color-text-muted);
            border: none;
            transition: all 0.2s;
        }
        .format-tab:hover {
            background: var(--color-border);
            color: var(--color-text);
        }
        .format-tab.active {
            background: var(--color-accent);
            color: #fff;
        }
        .format-tab:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }
        .inspector-html-content {
            background: #fff;
            color: #333;
            padding: 12px;
            border-radius: var(--radius-md);
            font-family: var(--font-sans);
        }

        /* Legend */
        .legend {
            position: fixed;
            bottom: 16px;
            left: 16px;
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
            padding: 12px 16px;
            display: flex;
            gap: 20px;
            font-size: 12px;
            z-index: 100;
            box-shadow: var(--shadow-md);
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--color-text-muted);
        }
        .legend-dot {
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }
        .legend-dot.pipe {
            background: var(--color-pipe);
        }
        .legend-dot.stuff {
            background: var(--color-stuff);
            border-radius: 6px;
        }
        .legend-dot.success {
            background: var(--color-success);
        }
        .legend-dot.error {
            background: var(--color-error);
        }

        /* Hint */
        .hint {
            position: fixed;
            bottom: 16px;
            right: 16px;
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--radius-md);
            padding: 10px 14px;
            font-size: 12px;
            color: var(--color-text-dim);
            z-index: 100;
            box-shadow: var(--shadow-md);
        }
    </style>
</head>
<body>
    <div id="app-container">
        <header class="header">
            <div class="header-left">
                <img src="{{ logo_url }}" alt="Pipelex" class="header-logo">
                <span class="header-title">{{ title }}</span>
            </div>
            <div class="header-stats" id="header-stats"></div>
        </header>
        <div id="root"></div>
    </div>

    <div id="inspector" class="inspector-panel">
        <div class="inspector-header" id="inspector-header">
            <div>
                <div id="inspector-title" class="inspector-title">Node Details</div>
                <div id="inspector-subtitle" class="inspector-subtitle"></div>
            </div>
            <span class="inspector-close" onclick="closeInspector()">&times;</span>
        </div>
        <div id="inspector-content" class="inspector-content"></div>
    </div>

    <div class="legend">
        <div class="legend-item"><div class="legend-dot pipe"></div>Pipe</div>
        <div class="legend-item"><div class="legend-dot stuff"></div>Data</div>
        <div class="legend-item"><div class="legend-dot success"></div>Success</div>
        <div class="legend-item"><div class="legend-dot error"></div>Failed</div>
    </div>

    <div class="hint">Click on nodes to view details</div>

    <!-- Embedded ViewSpec -->
    <script type="application/json" id="pipelex-viewspec">{{ viewspec_json }}</script>
    {% if graphspec_json %}
    <!-- Embedded GraphSpec (for dataflow extraction) -->
    <script type="application/json" id="pipelex-graphspec">{{ graphspec_json }}</script>
    {% endif %}
    <!-- Embedded stuff data in multiple formats for display toggle -->
    <script type="application/json" id="pipelex-stuff-data-text">{{ stuff_data_text_json }}</script>
    <script type="application/json" id="pipelex-stuff-data-html">{{ stuff_data_html_json }}</script>

    <script>
        // Parse embedded ViewSpec
        const viewspecElement = document.getElementById('pipelex-viewspec');
        const viewspec = JSON.parse(viewspecElement.textContent);

        // Parse GraphSpec if present
        const graphspecElement = document.getElementById('pipelex-graphspec');
        const graphspec = graphspecElement ? JSON.parse(graphspecElement.textContent) : null;

        // Parse stuff data in alternate formats (for display toggle)
        const stuffDataTextElement = document.getElementById('pipelex-stuff-data-text');
        const stuffDataText = stuffDataTextElement ? JSON.parse(stuffDataTextElement.textContent || '{}') : {};
        const stuffDataHtmlElement = document.getElementById('pipelex-stuff-data-html');
        const stuffDataHtml = stuffDataHtmlElement ? JSON.parse(stuffDataHtmlElement.textContent || '{}') : {};

        // Track current format selection for stuff display
        let currentStuffFormat = 'json';

        // ====================================================================
        // DATAFLOW ANALYSIS: Extract stuff nodes and build producer/consumer maps
        // This mirrors the Python GraphAnalysis logic
        // ====================================================================
        function buildDataflowAnalysis(graphspec) {
            if (!graphspec) return null;

            const stuffRegistry = {};      // digest -> { name, concept, data, dataText, dataHtml }
            const stuffProducers = {};     // digest -> producer_node_id
            const stuffConsumers = {};     // digest -> [consumer_node_ids]
            const containmentTree = {};    // parent_id -> [child_ids]
            const childNodeIds = new Set();

            // Build containment tree from edges
            for (const edge of graphspec.edges) {
                if (edge.kind === 'contains') {
                    if (!containmentTree[edge.source]) containmentTree[edge.source] = [];
                    containmentTree[edge.source].push(edge.target);
                    childNodeIds.add(edge.target);
                }
            }

            // Controller IDs are nodes that have children
            const controllerNodeIds = new Set(Object.keys(containmentTree));

            // Process nodes for stuff extraction
            for (const node of graphspec.nodes) {
                // Skip controllers - they don't directly transform data
                if (controllerNodeIds.has(node.node_id)) continue;

                const nodeIo = node.node_io || {};

                // Collect outputs (this node produces these stuffs)
                for (const output of (nodeIo.outputs || [])) {
                    if (output.digest) {
                        stuffRegistry[output.digest] = {
                            name: output.name,
                            concept: output.concept,
                            data: output.data,
                            dataText: output.data_text,
                            dataHtml: output.data_html,
                        };
                        stuffProducers[output.digest] = node.node_id;
                    }
                }

                // Collect inputs (this node consumes these stuffs)
                for (const input of (nodeIo.inputs || [])) {
                    if (input.digest) {
                        // Register stuff even if we don't know the producer (pipeline input)
                        if (!stuffRegistry[input.digest]) {
                            stuffRegistry[input.digest] = {
                                name: input.name,
                                concept: input.concept,
                                data: input.data,
                                dataText: input.data_text,
                                dataHtml: input.data_html,
                            };
                        }
                        if (!stuffConsumers[input.digest]) stuffConsumers[input.digest] = [];
                        stuffConsumers[input.digest].push(node.node_id);
                    }
                }
            }

            return {
                stuffRegistry,
                stuffProducers,
                stuffConsumers,
                controllerNodeIds,
                childNodeIds,
            };
        }

        const dataflowAnalysis = buildDataflowAnalysis(graphspec);
        const hasDataflow = dataflowAnalysis && Object.keys(dataflowAnalysis.stuffRegistry).length > 0;

        // Update header stats
        const statsEl = document.getElementById('header-stats');
        const pipeCount = hasDataflow
            ? graphspec.nodes.filter(n => !dataflowAnalysis.controllerNodeIds.has(n.node_id)).length
            : viewspec.nodes.length;
        const stuffCount = hasDataflow ? Object.keys(dataflowAnalysis.stuffRegistry).length : 0;
        const succeededCount = viewspec.nodes.filter(n => n.status === 'succeeded').length;
        const failedCount = viewspec.nodes.filter(n => n.status === 'failed').length;

        statsEl.innerHTML = `
            <div class="stat-item">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                </svg>
                <span class="stat-value">${pipeCount}</span> pipes
            </div>
            ${stuffCount > 0 ? `<div class="stat-item" style="color: var(--color-stuff)">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <ellipse cx="12" cy="12" rx="10" ry="6"/>
                </svg>
                <span class="stat-value">${stuffCount}</span> data
            </div>` : ''}
            ${succeededCount > 0 ? `<div class="stat-item" style="color: var(--color-success)">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span class="stat-value">${succeededCount}</span>
            </div>` : ''}
            ${failedCount > 0 ? `<div class="stat-item" style="color: var(--color-error)">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
                <span class="stat-value">${failedCount}</span>
            </div>` : ''}
        `;

        // ReactFlow setup
        const { React, ReactDOM } = window;
        const ReactFlowLib = window.ReactFlowRenderer || window.ReactFlow || {};
        const { ReactFlow, useNodesState, useEdgesState, Background, Controls, MiniMap, MarkerType } = ReactFlowLib;

        // Dagre layout function
        function getLayoutedElements(nodes, edges, direction = 'TB') {
            const g = new dagre.graphlib.Graph();
            g.setDefaultEdgeLabel(() => ({}));
            g.setGraph({
                rankdir: direction,
                nodesep: 50,
                ranksep: 80,
                edgesep: 20,
                marginx: 40,
                marginy: 40,
            });

            nodes.forEach((node) => {
                const nodeData = node.data || {};
                const isStuff = nodeData.isStuff;
                const width = isStuff ? 180 : 200;
                const height = isStuff ? 50 : 60;
                g.setNode(node.id, { width, height });
            });

            edges.forEach((edge) => {
                g.setEdge(edge.source, edge.target);
            });

            dagre.layout(g);

            const layoutedNodes = nodes.map((node) => {
                const nodeWithPosition = g.node(node.id);
                const nodeData = node.data || {};
                const isStuff = nodeData.isStuff;
                const width = isStuff ? 180 : 200;
                return {
                    ...node,
                    position: {
                        x: nodeWithPosition.x - width / 2,
                        y: nodeWithPosition.y - 30,
                    },
                };
            });

            return { nodes: layoutedNodes, edges };
        }

        // ====================================================================
        // BUILD DATAFLOW NODES AND EDGES
        // ====================================================================
        function buildDataflowGraph(graphspec, analysis) {
            const nodes = [];
            const edges = [];
            const nodeIdMap = {};  // original node_id -> graphspec node

            // Map node IDs to nodes
            for (const node of graphspec.nodes) {
                nodeIdMap[node.node_id] = node;
            }

            // Find participating pipes (those that produce or consume data)
            const participatingPipes = new Set();
            for (const producer of Object.values(analysis.stuffProducers)) {
                participatingPipes.add(producer);
            }
            for (const consumers of Object.values(analysis.stuffConsumers)) {
                for (const consumer of consumers) {
                    participatingPipes.add(consumer);
                }
            }

            // Create pipe nodes (only those that participate in data flow)
            for (const node of graphspec.nodes) {
                if (!participatingPipes.has(node.node_id)) continue;

                const isFailed = node.status === 'failed';
                const label = node.pipe_code || node.node_id.split(':').pop();

                nodes.push({
                    id: node.node_id,
                    type: 'default',
                    data: {
                        label: React.createElement('div', {
                            style: {
                                padding: '10px 14px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '2px',
                                textAlign: 'center',
                            }
                        },
                            React.createElement('span', {
                                style: {
                                    fontFamily: "'JetBrains Mono', monospace",
                                    fontSize: '13px',
                                    fontWeight: 600,
                                    color: '#f1f5f9',
                                }
                            }, label)
                        ),
                        nodeData: node,
                        isPipe: true,
                        isStuff: false,
                    },
                    position: { x: 0, y: 0 },
                    style: {
                        background: isFailed ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.1)',
                        border: isFailed ? '2px solid #ef4444' : '2px solid #3b82f6',
                        borderRadius: '8px',
                        padding: '0',
                        minWidth: '160px',
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                    },
                });
            }

            // Create stuff nodes
            for (const [digest, stuffInfo] of Object.entries(analysis.stuffRegistry)) {
                const stuffId = `stuff_${digest}`;
                const label = stuffInfo.name;
                const concept = stuffInfo.concept || '';

                nodes.push({
                    id: stuffId,
                    type: 'default',
                    data: {
                        label: React.createElement('div', {
                            style: {
                                padding: '8px 16px',
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                gap: '2px',
                                textAlign: 'center',
                            }
                        },
                            React.createElement('span', {
                                style: {
                                    fontFamily: "'JetBrains Mono', monospace",
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    color: '#f1f5f9',
                                }
                            }, label),
                            concept && React.createElement('span', {
                                style: {
                                    fontSize: '10px',
                                    color: '#94a3b8',
                                }
                            }, concept)
                        ),
                        stuffData: stuffInfo,
                        stuffDigest: digest,
                        isStuff: true,
                        isPipe: false,
                    },
                    position: { x: 0, y: 0 },
                    style: {
                        background: 'rgba(245, 158, 11, 0.15)',
                        border: '2px solid #d97706',
                        borderRadius: '999px',  // Pill shape
                        padding: '0',
                        minWidth: '140px',
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                        cursor: 'pointer',
                    },
                });
            }

            // Create edges: producer -> stuff
            let edgeId = 0;
            for (const [digest, producerNodeId] of Object.entries(analysis.stuffProducers)) {
                const stuffId = `stuff_${digest}`;
                edges.push({
                    id: `edge_${edgeId++}`,
                    source: producerNodeId,
                    target: stuffId,
                    type: 'smoothstep',
                    animated: false,
                    style: {
                        stroke: '#3b82f6',
                        strokeWidth: 2,
                    },
                    markerEnd: {
                        type: MarkerType?.ArrowClosed || 'arrowclosed',
                        color: '#3b82f6',
                    },
                });
            }

            // Create edges: stuff -> consumer
            for (const [digest, consumers] of Object.entries(analysis.stuffConsumers)) {
                const stuffId = `stuff_${digest}`;
                for (const consumerNodeId of consumers) {
                    edges.push({
                        id: `edge_${edgeId++}`,
                        source: stuffId,
                        target: consumerNodeId,
                        type: 'smoothstep',
                        animated: false,
                        style: {
                            stroke: '#3b82f6',
                            strokeWidth: 2,
                        },
                        markerEnd: {
                            type: MarkerType?.ArrowClosed || 'arrowclosed',
                            color: '#3b82f6',
                        },
                    });
                }
            }

            return { nodes, edges };
        }

        // ====================================================================
        // FALLBACK: Build orchestration graph from ViewSpec (no dataflow)
        // ====================================================================
        function buildOrchestrationGraph(viewspec) {
            const nodes = viewspec.nodes.map(node => {
                const isController = node.kind === 'controller';
                const isFailed = node.ui?.classes?.includes('failed');
                const isSucceeded = node.ui?.classes?.includes('succeeded');
                const badge = node.ui?.badges?.[0] || '';

                return {
                    id: node.id,
                    type: 'default',
                    data: {
                        label: React.createElement('div', {
                            style: {
                                padding: '10px 14px',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '4px',
                            }
                        },
                            React.createElement('div', {
                                style: {
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: '8px',
                                }
                            },
                                React.createElement('span', {
                                    style: {
                                        fontFamily: "'JetBrains Mono', monospace",
                                        fontSize: '13px',
                                        fontWeight: 600,
                                        color: '#f1f5f9',
                                    }
                                }, node.label),
                                isSucceeded && React.createElement('span', {
                                    style: {
                                        width: '8px',
                                        height: '8px',
                                        borderRadius: '50%',
                                        background: '#10b981',
                                        flexShrink: 0,
                                    }
                                }),
                                isFailed && React.createElement('span', {
                                    style: {
                                        width: '8px',
                                        height: '8px',
                                        borderRadius: '50%',
                                        background: '#ef4444',
                                        flexShrink: 0,
                                    }
                                })
                            ),
                            React.createElement('div', {
                                style: {
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    gap: '8px',
                                }
                            },
                                React.createElement('span', {
                                    style: {
                                        fontSize: '11px',
                                        color: '#64748b',
                                    }
                                }, isController ? 'Controller' : node.inspector?.pipe_type || 'Operator'),
                                badge && React.createElement('span', {
                                    style: {
                                        fontSize: '10px',
                                        color: '#94a3b8',
                                        background: 'rgba(255,255,255,0.1)',
                                        padding: '2px 6px',
                                        borderRadius: '4px',
                                        fontFamily: "'JetBrains Mono', monospace",
                                    }
                                }, badge)
                            )
                        ),
                        nodeData: node,
                        isPipe: true,
                        isStuff: false,
                    },
                    position: node.position || { x: 0, y: 0 },
                    style: {
                        background: isFailed ? 'rgba(239, 68, 68, 0.15)' : (isController ? 'rgba(139, 92, 246, 0.1)' : 'rgba(6, 182, 212, 0.1)'),
                        border: `2px solid ${isFailed ? '#ef4444' : (isController ? '#8b5cf6' : '#06b6d4')}`,
                        borderRadius: '8px',
                        padding: '0',
                        minWidth: '160px',
                        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                    },
                };
            });

            const edges = viewspec.edges.map(edge => ({
                id: edge.id,
                source: edge.source,
                target: edge.target,
                type: 'smoothstep',
                animated: edge.animated || false,
                label: edge.label,
                labelStyle: {
                    fontSize: 11,
                    fontWeight: 500,
                    fill: '#94a3b8',
                    fontFamily: "'JetBrains Mono', monospace",
                },
                labelBgStyle: {
                    fill: '#0f172a',
                    fillOpacity: 0.9,
                },
                labelBgPadding: [6, 4],
                labelBgBorderRadius: 4,
                style: {
                    stroke: edge.kind === 'data' ? '#3b82f6' : '#475569',
                    strokeWidth: edge.kind === 'data' ? 2 : 1,
                },
                markerEnd: {
                    type: MarkerType?.ArrowClosed || 'arrowclosed',
                    color: edge.kind === 'data' ? '#3b82f6' : '#475569',
                },
            }));

            return { nodes, edges };
        }

        // ====================================================================
        // MAIN REACT COMPONENT
        // ====================================================================
        function GraphViewer() {
            // Build graph based on available data
            let initialData;
            if (hasDataflow) {
                initialData = buildDataflowGraph(graphspec, dataflowAnalysis);
            } else {
                initialData = buildOrchestrationGraph(viewspec);
            }

            // Apply layout
            const needsLayout = initialData.nodes.some(n => !n.position || (n.position.x === 0 && n.position.y === 0));
            const layouted = needsLayout
                ? getLayoutedElements(initialData.nodes, initialData.edges, viewspec.layout?.direction || 'TB')
                : initialData;

            const [nodes, setNodes, onNodesChange] = useNodesState(layouted.nodes);
            const [edges, setEdges, onEdgesChange] = useEdgesState(layouted.edges);

            const onNodeClick = (event, node) => {
                const inspector = document.getElementById('inspector');
                const inspectorContent = document.getElementById('inspector-content');
                const inspectorTitle = document.getElementById('inspector-title');
                const inspectorSubtitle = document.getElementById('inspector-subtitle');
                const inspectorHeader = document.getElementById('inspector-header');

                const nodeData = node.data || {};

                // Handle stuff nodes
                if (nodeData.isStuff) {
                    const stuffData = nodeData.stuffData || {};
                    const stuffDigest = nodeData.stuffDigest;
                    const stuffMermaidId = stuffDigest ? `s_${stuffDigest.substring(0, 10)}` : null;

                    inspectorTitle.textContent = stuffData.name || 'Data';
                    inspectorSubtitle.textContent = stuffData.concept || 'Data Item';
                    inspectorHeader.className = 'inspector-header stuff';

                    // Check which formats are available
                    // First check graphspec-extracted data, then fallback to separate dictionaries
                    const hasJson = !!stuffData.data;
                    const hasText = !!stuffData.dataText || (stuffMermaidId && !!stuffDataText[stuffMermaidId]);
                    const hasHtml = !!stuffData.dataHtml || (stuffMermaidId && !!stuffDataHtml[stuffMermaidId]);
                    const hasMultipleFormats = [hasJson, hasText, hasHtml].filter(Boolean).length > 1;

                    let html = '';
                    html += '<div class="inspector-badges">';
                    html += '<span class="inspector-badge stuff">📦 Data Item</span>';
                    html += '</div>';

                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Name</div>
                        <div class="inspector-value pipe-code">${stuffData.name || 'N/A'}</div>
                    </div>`;

                    if (stuffData.concept) {
                        html += `<div class="inspector-section">
                            <div class="inspector-section-title">Concept</div>
                            <div class="inspector-value">${stuffData.concept}</div>
                        </div>`;
                    }

                    // Add format tabs if multiple formats available
                    if (hasMultipleFormats) {
                        html += '<div class="inspector-section">';
                        html += '<div class="inspector-section-title">Data Content</div>';
                        html += '<div class="format-tabs" id="stuff-format-tabs">';
                        const jsonActive = currentStuffFormat === 'json' ? 'active' : '';
                        const textActive = currentStuffFormat === 'text' ? 'active' : '';
                        const htmlActive = currentStuffFormat === 'html' ? 'active' : '';
                        html += `<button class="format-tab ${jsonActive}" data-format="json" `;
                        html += `${!hasJson ? 'disabled' : ''}>JSON</button>`;
                        html += `<button class="format-tab ${textActive}" data-format="text" `;
                        html += `${!hasText ? 'disabled' : ''}>Pretty</button>`;
                        html += `<button class="format-tab ${htmlActive}" data-format="html" `;
                        html += `${!hasHtml ? 'disabled' : ''}>HTML</button>`;
                        html += '</div>';
                        html += '<div id="stuff-data-content"></div>';
                        html += '</div>';
                    } else if (hasJson || hasText || hasHtml) {
                        html += '<div class="inspector-section">';
                        html += '<div class="inspector-section-title">Data Content</div>';
                        html += '<div id="stuff-data-content"></div>';
                        html += '</div>';
                    }

                    inspectorContent.innerHTML = html;

                    // Store current stuff data for format switching
                    window.currentStuffJsonData = stuffData.data;
                    window.currentStuffMermaidId = stuffMermaidId;
                    // Store graphspec-extracted text/html data (preferred over dictionary lookups)
                    window.currentStuffDataText = stuffData.dataText;
                    window.currentStuffDataHtml = stuffData.dataHtml;

                    // Attach format tab handlers
                    const formatTabs = document.getElementById('stuff-format-tabs');
                    if (formatTabs) {
                        formatTabs.querySelectorAll('.format-tab').forEach(tab => {
                            tab.addEventListener('click', () => {
                                if (tab.disabled) return;
                                setStuffFormat(tab.dataset.format);
                            });
                        });
                    }

                    // Render initial content
                    if (hasJson || hasText || hasHtml) {
                        // Determine best available format
                        let bestFormat = currentStuffFormat;
                        if (bestFormat === 'json' && !hasJson) bestFormat = hasText ? 'text' : 'html';
                        if (bestFormat === 'text' && !hasText) bestFormat = hasJson ? 'json' : 'html';
                        if (bestFormat === 'html' && !hasHtml) bestFormat = hasJson ? 'json' : 'text';

                        renderStuffContent(bestFormat);
                    }

                    inspector.classList.add('visible');
                    return;
                }

                // Handle pipe nodes
                const pipeData = nodeData.nodeData || {};
                inspectorTitle.textContent = pipeData.pipe_code || pipeData.label || node.id;
                inspectorSubtitle.textContent = pipeData.pipe_type || nodeData.kind || 'Pipe';
                inspectorHeader.className = 'inspector-header pipe';

                const timing = pipeData.timing;
                const nodeIo = pipeData.node_io;
                const status = pipeData.status;

                let html = '';

                // Status badges
                html += '<div class="inspector-badges">';
                if (status === 'succeeded') {
                    html += '<span class="inspector-badge success">✓ Succeeded</span>';
                } else if (status === 'failed') {
                    html += '<span class="inspector-badge error">✕ Failed</span>';
                }
                if (timing?.duration_ms) {
                    html += `<span class="inspector-badge neutral">⏱ ${timing.duration_ms}ms</span>`;
                }
                html += '</div>';

                // Pipe info
                if (pipeData.pipe_code) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Pipe Code</div>
                        <div class="inspector-value pipe-code">${pipeData.pipe_code}</div>
                    </div>`;
                }

                if (pipeData.pipe_type) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Pipe Type</div>
                        <div class="inspector-value">${pipeData.pipe_type}</div>
                    </div>`;
                }

                if (timing) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Timing</div>
                        <div class="inspector-row">
                            <span class="inspector-row-label">Started</span>
                            <span class="inspector-row-value">${new Date(timing.started_at).toLocaleTimeString()}</span>
                        </div>
                        <div class="inspector-row">
                            <span class="inspector-row-label">Ended</span>
                            <span class="inspector-row-value">${new Date(timing.ended_at).toLocaleTimeString()}</span>
                        </div>
                        <div class="inspector-row">
                            <span class="inspector-row-label">Duration</span>
                            <span class="inspector-row-value">${timing.duration_ms}ms</span>
                        </div>
                    </div>`;
                }

                if (nodeIo?.inputs?.length > 0) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Inputs (${nodeIo.inputs.length})</div>
                        <div class="inspector-pre">${nodeIo.inputs.map(i => `${i.name}: ${i.concept || 'unknown'}`).join('\\n')}</div>
                    </div>`;
                }

                if (nodeIo?.outputs?.length > 0) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Outputs (${nodeIo.outputs.length})</div>
                        <div class="inspector-pre">${nodeIo.outputs.map(o => `${o.name}: ${o.concept || 'unknown'}`).join('\\n')}</div>
                    </div>`;
                }

                if (pipeData.error) {
                    html += `<div class="inspector-section">
                        <div class="inspector-section-title">Error</div>
                        <pre class="inspector-pre" style="color: var(--color-error);">${JSON.stringify(pipeData.error, null, 2)}</pre>
                    </div>`;
                }

                inspectorContent.innerHTML = html || '<div style="color: var(--color-text-dim)">No additional information</div>';
                inspector.classList.add('visible');
            };

            if (!ReactFlow) {
                return React.createElement('div', { style: { padding: '20px', color: '#f1f5f9' } },
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
                    fitViewOptions: { padding: 0.2 },
                    defaultEdgeOptions: { type: 'smoothstep' },
                    proOptions: { hideAttribution: true },
                },
                    Background ? React.createElement(Background, {
                        variant: 'dots',
                        gap: 20,
                        size: 1,
                        color: '#334155',
                    }) : null,
                    Controls ? React.createElement(Controls, { showInteractive: false }) : null,
                    MiniMap ? React.createElement(MiniMap, {
                        nodeColor: (n) => {
                            if (n.data?.isStuff) return '#f59e0b';
                            const status = n.data?.nodeData?.status;
                            if (status === 'failed') return '#ef4444';
                            return '#3b82f6';
                        },
                        maskColor: 'rgba(15, 23, 42, 0.8)',
                        style: { background: '#1e293b' },
                    }) : null
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

        // Set stuff display format and re-render
        function setStuffFormat(format) {
            currentStuffFormat = format;
            // Update tab styling
            document.querySelectorAll('.format-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.format === format);
            });
            renderStuffContent(format);
        }

        // Render stuff content in the specified format
        function renderStuffContent(format) {
            const container = document.getElementById('stuff-data-content');
            if (!container) return;

            const stuffMermaidId = window.currentStuffMermaidId;
            const jsonData = window.currentStuffJsonData;
            // Prefer graphspec-extracted data, fallback to dictionary lookups
            const textData = window.currentStuffDataText || (stuffMermaidId && stuffDataText[stuffMermaidId]);
            const htmlData = window.currentStuffDataHtml || (stuffMermaidId && stuffDataHtml[stuffMermaidId]);

            if (format === 'json') {
                container.className = '';
                const jsonStr = JSON.stringify(jsonData, null, 2);
                container.innerHTML = `<pre class="inspector-pre">${escapeHtml(jsonStr)}</pre>`;
            } else if (format === 'text') {
                // Use nowrap class for Rich-formatted ASCII tables
                const textContent = textData || 'No text data available';
                container.className = '';
                container.innerHTML = `<pre class="inspector-pre nowrap">${escapeHtml(textContent)}</pre>`;
            } else if (format === 'html') {
                const htmlContent = htmlData || 'No HTML data available';
                container.className = 'inspector-html-content';
                container.innerHTML = htmlContent;
            }
        }

        // Escape HTML to prevent XSS when displaying JSON/text content
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
"""


def generate_reactflow_html(
    viewspec: ViewSpec,
    *,
    graphspec: GraphSpec | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    use_cdn: bool = True,
    title: str = "Pipelex Graph",
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer.

    Args:
        viewspec: The ViewSpec to embed and render.
        graphspec: Optional GraphSpec to embed (for inspector details).
        stuff_data_text: Optional mapping from stuff IDs to their ASCII text representation.
        stuff_data_html: Optional mapping from stuff IDs to their HTML representation.
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
            "logo_url": URLs.logo_white_on_transparent,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "stuff_data_text_json": json.dumps(stuff_data_text or {}),
            "stuff_data_html_json": json.dumps(stuff_data_html or {}),
            "use_cdn": use_cdn,
        },
    )


async def generate_reactflow_html_async(
    viewspec: ViewSpec,
    *,
    graphspec: GraphSpec | None = None,
    stuff_data_text: dict[str, str] | None = None,
    stuff_data_html: dict[str, str] | None = None,
    use_cdn: bool = True,
    title: str = "Pipelex Graph",
) -> str:
    """Generate single-file HTML with embedded ViewSpec and ReactFlow viewer (async version).

    Use this when inside an async event loop.

    Args:
        viewspec: The ViewSpec to embed and render.
        graphspec: Optional GraphSpec to embed (for inspector details).
        stuff_data_text: Optional mapping from stuff IDs to their ASCII text representation.
        stuff_data_html: Optional mapping from stuff IDs to their HTML representation.
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
            "logo_url": URLs.logo_white_on_transparent,
            "viewspec_json": viewspec_json,
            "graphspec_json": graphspec_json,
            "stuff_data_text_json": json.dumps(stuff_data_text or {}),
            "stuff_data_html_json": json.dumps(stuff_data_html or {}),
            "use_cdn": use_cdn,
        },
    )
