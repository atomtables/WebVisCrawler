import argparse
import networkx as nx
import tempfile
import json
import webbrowser
import os
from urllib.parse import urlparse
from collections import deque
import sys


def truncate_middle(s, n):
    if len(s) <= n:
        # string is already short-enough
        return s
    # half of the size, minus the 3 .'s
    n_2 = int(int(n) / 2 - 3)
    # whatever's left
    n_1 = int(n - n_2 - 3)
    return '{0}...{1}'.format(s[:n_1], s[-n_2:])


class WebVisCrawlVis:
    def __init__(self):
        # Graph data
        self.nodes = {}
        self.edges = []
        self.graph = None
        self.temp_html_path = None
        self.head = "https://hackclub.com"

    @staticmethod
    def _get_domain(url):
        try:
            domain = urlparse(url).netloc
            return domain if domain else url[:30]
        except (Exception,):
            return url[:30]

    def _parse_adjacency_file(self, obj):
        nodes = {}
        edges = []
        queuex = [self.head]
        while len(queuex) > 0:
            current = queuex.pop()
            if current not in obj:
                nodes[current] = {'status': 'errored', 'level': 0}
                continue
            if current.endswith("::F:"):
                nodes[current.removesuffix("::F:")] = {'status': 'errored', 'level': 0}
                continue
            current = current.removesuffix("::F:")
            if current in nodes:
                continue
            nodes[current] = {'status': "normal", 'level': 0}
            for link in obj[current]:
                if link not in nodes:
                    queuex.append(link)
                edges.append((current, link))

        return nodes, edges

    def _process_nodes(self):
        # Create NetworkX graph
        self.graph = nx.DiGraph()

        # Add nodes with attributes
        for url, attrs in self.nodes.items():
            self.graph.add_node(url, **attrs)

        # Add edges
        for parent, child in self.edges:
            self.graph.add_edge(parent, child)

        print(f"Loaded graph with {len(self.nodes)} nodes and {len(self.edges)} edges")
        return True

    def create_graph(self, file_path):
        with open(file_path, 'r') as f:
            obj = json.loads(f.read())
            self.nodes, self.edges = self._parse_adjacency_file(obj)

        if not self.nodes:
            print("Error: Failed to parse the file or file is empty.")
            return False

        self._process_nodes()

        print(f"Loaded graph with {len(self.nodes)} nodes and {len(self.edges)} edges")
        return True

    def create_graph_from_py(self, adjacency_file, head):
        """Parse the adjacency file and create a NetworkX graph."""
        self.nodes, self.edges = self._parse_adjacency_file(adjacency_file)
        self.head = head

        if not self.nodes:
            print("Error: Failed to parse the file or file is empty.")
            return False

        self._process_nodes()
        print(f"Loaded graph with {len(self.nodes)} nodes and {len(self.edges)} edges")
        return True

    def create_pyvis_graph(self, max_nodes=1000, show_labels=True, physics_enabled=False, output_file=None, line_physics_enabled=False):
        """Create and display a PyVis visualization of the graph."""
        if not self.graph:
            print("Error: No graph loaded. Load a graph first.")
            return False

        print(f"Preparing visualization with max {max_nodes} nodes...")

        # Create a subgraph if needed
        if len(self.graph) > max_nodes:
            # Take nodes in BFS order from the roots
            roots = [n for n, d in self.graph.in_degree() if d == 0]
            if not roots:
                roots = list(self.graph.nodes())[:1]

            # Use a proper BFS to select nodes
            nodes = set()
            queue = deque(roots)
            while queue and len(nodes) < max_nodes:
                current = queue.popleft()
                if current not in nodes:
                    nodes.add(current)
                    # Add neighbors to queue
                    neighbors = list(self.graph.neighbors(current))
                    queue.extend([n for n in neighbors if n not in nodes])

            subgraph = self.graph.subgraph(nodes)
        else:
            subgraph = self.graph

        # Prepare nodes and edges data
        nodes_data = []
        for node, attrs in subgraph.nodes(data=True):
            # Set node color based on status
            color = "#5DADE2"  # Default blue
            if attrs.get('status') == 'errored':
                color = "#E74C3C"  # Red
            elif node == self.head:
                color = "#27AE60"  # Green for root
            elif len(list(subgraph.predecessors(node))) == 1 and len(list(subgraph.neighbors(node))) == 0:
                color = "#95A5A6" # nodes with 1 parent and no children
            elif len(list(subgraph.predecessors(node))) == 1:
                color = "#F39C12" # single-raised
            elif len(list(subgraph.neighbors(node))) == 0:
                color = "#8E44AD" # bachelors

            nodes_data.append({
                "id": node,
                "label": truncate_middle(node, 30) if show_labels else "",
                "title": f"{node}\nIncoming connections: {len(list(subgraph.predecessors(node)))}\nOutgoing connections: {len(list(subgraph.neighbors(node)))}",
                "color": color,
                "shape": "dot" if attrs.get('status') != 'errored' else "square",
                "size": 10 + len(list(subgraph.neighbors(node))) + len(list(subgraph.predecessors(node))),
                "borderWidth": 1,
                "font": {"size": 12}
            })

        edges_data = []
        for source, target in subgraph.edges():
            edges_data.append({
                "from": source,
                "to": target,
                "arrows": "to",
                "physics": line_physics_enabled
            })

        # Create HTML file path
        if output_file:
            self.temp_html_path = output_file
        else:
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as tmp:
                self.temp_html_path = tmp.name

        # Generate HTML content
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Web Crawler Visualization</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network@10.0.1/dist/vis-network.min.js"></script>
    <link href="https://unpkg.com/vis-network@10.0.1/styles/vis-network.min.css" rel="stylesheet" type="text/css" />
    <style type="text/css">
        #mynetwork {{
            width: 100%;
            height: 100vh;
            border: 1px solid lightgray;
            background-color: #f9f9f9;
        }}
        body {{
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }}
        #controls {{
            position: absolute;
            top: 10px;
            left: 10px;
            z-index: 999;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.2);
        }}
        button {{
            margin: 2px;
            padding: 5px 10px;
            cursor: pointer;
        }}
        #info {{
            position: absolute;
            bottom: 10px;
            right: 10px;
            z-index: 999;
            background-color: rgba(255, 255, 255, 0.8);
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.2);
        }}
        html, body {{
            width: 100vw;
            height: 100vh;
            margin: 0;
            padding: 0;
            overflow: hidden;
            font-family: Arial, sans-serif;
        }}
        #mynetwork {{
            width: 100vw;
            height: 100vh;
            border: 1px solid lightgray;
            background-color: #f9f9f9;
            position: absolute;
            top: 0;
            left: 0;
            overflow: hidden;
        }}
        #controls, #info, #main {{
            z-index: 999;
        }}
    </style>
</head>
<body>
    <div id="main" style="position: fixed; bottom: 10px; left: 10px; z-index: 999;"></div>
    <div id="mynetwork"></div>
    <div id="controls">
        <button onclick="zoomIn()">Zoom In</button>
        <button onclick="zoomOut()">Zoom Out</button>
        <button onclick="resetView()">Reset View</button>
        <button onclick="togglePhysics()">Toggle Physics</button>
        <button onclick="showEverything()">Show All</button>
        <button onclick="hideBachelors()">Hide Bachelors</button>
        <button onclick="hideSingles()">Hide Singles</button>
        <button onclick="hideBoth()">Hide Both</button>
    </div>
    <div id="info">
        <div id="shelf" style="max-width: 300px; display: flex; flex-direction: row; flex-wrap: wrap; gap: 5px;">
        </div>
        <p>Nodes: <span id="nodes">{len(subgraph.nodes)}</span> of {len(self.graph.nodes)}, Edges: {len(subgraph.edges)}</p>
        <p>Zoom with mouse wheel, pan by dragging</p>
        <p>Click on nodes to select and move them</p>
    </div>
    <script type="text/javascript">
        // Direct node and edge data embedding
        var nodes = new vis.DataSet({json.dumps(nodes_data)});
        var edges = new vis.DataSet({json.dumps(edges_data)});

        var container = document.getElementById('mynetwork');
        var data = {{
            nodes: nodes,
            edges: edges
        }};

        var options = {{
            "configure": {{
                "enabled": false
            }},
            "layout": {{
                "improvedLayout": false
            }},
            "edges": {{
                "color": {{
                    "inherit": true
                }},
                "smooth": {{
                    "enabled": true,
                    "type": "dynamic"
                }}
            }},
            "interaction": {{
                "dragNodes": true,
                "hideEdgesOnDrag": false,
                "hideNodesOnDrag": false
            }},
            "physics": {{
                "enabled": {str(physics_enabled).lower()},
                "stabilization": {{
                    "enabled": true,
                    "fit": true,
                    "iterations": 1000,
                    "onlyDynamicEdges": false,
                    "updateInterval": 50
                }}
            }}
        }};

        var network = new vis.Network(container, data, options);
        document.querySelector("#nodes").innerText = nodes.length;
        
        function showEverything() {{
            // delete current network
            network.destroy();
            network = new vis.Network(container, data, options);
            document.querySelector("#nodes").innerText = nodes.length;
        }}

        function hideBachelors() {{
            network.destroy();
            let toShow = [];
            nodes.forEach(function(node) {{
                if (node.color !== "#8E44AD") {{
                    toShow.push(node);
                }}
            }});
            let toEdge = []
            let ids = toShow.map(n => n.id);
            edges.forEach(function(edge) {{
                if (ids.includes(edge.from) && ids.includes(edge.to)) {{
                    toEdge.push(edge);
                }}
            }});
            let newData = {{
                nodes: toShow,
                edges: toEdge
            }}
            network = new vis.Network(container, newData, options);
            document.querySelector("#nodes").innerText = toShow.length;
        }}
        
        function hideSingles() {{
            network.destroy();
            let toShow = [];
            nodes.forEach(function(node) {{
                if (node.color !== "#F39C12") {{
                    toShow.push(node);
                }}
            }});
            let toEdge = []
            let ids = toShow.map(n => n.id);
            edges.forEach(function(edge) {{
                if (ids.includes(edge.from) && ids.includes(edge.to)) {{
                    toEdge.push(edge); 
                }}
            }}); 
            let newData = {{
                nodes: toShow,
                edges: toEdge
            }}
            network = new vis.Network(container, newData, options);
            document.querySelector("#nodes").innerText = toShow.length;
        }}
        
        function hideBoth() {{
        network.destroy();
            let toShow = [];
            nodes.forEach(function(node) {{
                if (node.color !== "#F39C12" && node.color !== "#8E44AD") {{
                    toShow.push(node);
                }}
            }});
            let toEdge = []
            let ids = toShow.map(n => n.id);
            edges.forEach(function(edge) {{
                if (ids.includes(edge.from) && ids.includes(edge.to)) {{
                    toEdge.push(edge);
                }}
            }});
            let newData = {{
                nodes: toShow,
                edges: toEdge
            }}      
            network = new vis.Network(container, newData, options);
            document.querySelector("#nodes").innerText = toShow.length;
        }}

        function zoomIn() {{
            network.zoomIn(0.2);
        }}

        function zoomOut() {{
            network.zoomOut(0.2);
        }}

        function resetView() {{
            network.fit();
        }}

        function togglePhysics() {{
            var physics = network.physics.options.enabled;
            network.setOptions({{ physics: {{ enabled: !physics }} }});
            if (!physics) {{
                network.stabilize();
                document.querySelector("#main").innerText = "Physics enabled.";
            }} else {{
                document.querySelector("#main").innerText = "Physics disabled.";
            }}
        }}

        network.on("doubleClick", function(params) {{
            if (params.nodes.length > 0) {{
                network.focus(params.nodes[0], {{
                    scale: 1.2,
                    animation: true
                }});
            }}
        }});
        
        // function to alert all outgoing connections of a node id using a confirm buffered by 50
        function showOutgoing(nodeId) {{
            var outgoing = network.getConnectedNodes(nodeId, 'to');
            if (outgoing.length === 0) {{
                alert("No other outgoing connections.");
                return;
            }}
            let count = 0;
            var first50 = outgoing.slice(count, count + 50);
            count += 50;
            while (first50.length > 0) {{
                if (confirm(first50.join('\\n') + "\\n Click OK to see more.")) {{
                    try {{
                        first50 = outgoing.slice(count, count + 50);
                        count += 50;
                    }} catch {{
                        first50 = outgoing.slice(count);
                    }}
                }} else {{
                    break;
                }}
            }}
            alert("done");
        }}
        
        function showIncoming(nodeId) {{
            var incoming = network.getConnectedNodes(nodeId, 'from');
            if (incoming.length === 1) {{
                alert("No other incoming connections.");
                return;
            }}
            let count = 0;
            var first50 = incoming.slice(count, count + 50);
            count += 50;
            while (first50.length > 0) {{
                if (confirm(first50.join('\\n') + "\\n Click OK to see more.")) {{
                    try {{
                        first50 = incoming.slice(count, count + 50);
                        count += 50;
                    }} catch {{
                        first50 = incoming.slice(count);
                    }}
                }} else {{
                    break;
                }}
            }}
            alert("done");
        }}
        
        network.on("click", function(params) {{
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodes.get(nodeId);
                document.querySelector("#shelf").innerHTML = `
                <strong>${{node.label}}</strong><br/>
                <button onClick="alert('${{nodeId}}')">Get URL</button>
                <button onClick="network.focus('${{nodeId}}', {{scale: 1.5, animation: true}})">Focus</button>
                <button onClick="showOutgoing('${{nodeId}}')">Show Outgoing connections</button>
                <button onClick="showIncoming('${{nodeId}}')">Show Incoming connections</button>
                `;
            }} else {{
                document.querySelector("#shelf").innerHTML = "";
            }}
        }});

        document.addEventListener("keydown", function(event) {{
            if (event.key === "+" || event.key === "=") {{
                zoomIn();
            }} else if (event.key === "-") {{
                zoomOut();
            }} else if (event.key === "0") {{
                resetView();
            }} else if (event.key === "p") {{
                togglePhysics();
            }}
        }});
    </script>
</body>
</html>'''

        try:
            # Write HTML to file
            with open(self.temp_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"Visualization created at: {self.temp_html_path}")
            return True
        except Exception as e:
            print(f"Error creating visualization: {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser(description='WebVisCrawl visualiser')
    parser.add_argument('input_file', nargs='?', default='adj.txt',
                        help='Path to adjacency file (default: adj.txt)')
    parser.add_argument('--head', nargs='?')
    parser.add_argument('-o', '--output', help='Output HTML file path')
    parser.add_argument('-n', '--max-nodes', type=int, default=10000,
                        help='Maximum number of nodes to display (default: 1000)')
    parser.add_argument('-l', '--no-labels', action='store_true',
                        help='Hide domain labels on nodes')
    parser.add_argument('-p', '--physics', action='store_true',
                        help='Show physics simulation (leave disabled for performance)')
    parser.add_argument('-b', '--no-browser', action='store_true',
                        help='Do not open visualization in browser')
    parser.add_argument('--line-physics-enabled', action='store_true',
                        help='Enable physics on edges (lines). Will cause thermonuclear war.')


    args = parser.parse_args()

    # Check if input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        return 1

    if not args.head:
        print("Error: Please provide the head URL as the second positional argument.")
        return 1

    # Create visualizer
    visualizer = WebVisCrawlVis()
    visualizer.head = args.head

    # Load graph
    if not visualizer.create_graph(args.input_file):
        return 1

    # Create visualization
    if not visualizer.create_pyvis_graph(
            max_nodes=args.max_nodes,
            show_labels=not args.no_labels,
            physics_enabled=args.physics,
            output_file=args.output,
            line_physics_enabled=args.line_physics_enabled
    ):
        return 1

    # Open in browser unless disabled
    if not args.no_browser:
        print(f"Opening visualization in browser...")
        webbrowser.open(f"file://{visualizer.temp_html_path}")

    return 0

if __name__ == "__main__":
    sys.exit(main())