"""
app.py

PatternVis Streamlit application.

app.py is responsible for the main user interface and control flow, including:
- collecting schema and SQL user input
- parsing the input query into components
- building a query graph from the parsed representation
- computing a layout for the graph
- rendering the graph with PyVis
- using custom HTML/CSS/JavaScript to highlight matching SQL clauses

This is the main UI/controller layer. 
No parsing logic or graph structure rules live here;
those responsibilities are delegated to parser.py and graph_builder.py.
"""

import streamlit as sl
import streamlit.components.v1 as components
import tempfile
import os
import html

from parser import parse_schema, parse_query_basic, explain_query
from graph_builder import build_query_graph
from pyvis.network import Network


def format_select_lines(select_clause: str) -> list[str]:
    """
    Split a SELECT clause into separate lines.
    """
    if not select_clause:
        return []

    return [part.strip() for part in select_clause.split(",")]


def build_visual_label(node_alias, data):
    """
    Build the visible label text shown inside each node.
    """
    table_name = data.get("table_name", node_alias)
    is_result_node = data.get("is_result_node", False)
    is_select_node = data.get("is_select_node", False)
    is_filter_node = data.get("is_filter_node", False)
    is_order_node = data.get("is_order_node", False)

    group_by_value = data.get("group_by", "")
    aggregates = data.get("aggregates", [])
    select_clause = data.get("select", "")
    filters = data.get("filters", [])
    order_by_value = data.get("order_by", "")

    # WHERE node: display the word WHERE plus each filter condition.
    if is_filter_node:
        label_lines = ["WHERE", ""]
        label_lines.extend(filters)
        return "\n".join(label_lines)

    # ORDER BY node: display the sort clause.
    if is_order_node:
        label_lines = ["ORDER BY", "", order_by_value]
        return "\n".join(label_lines)

    # SELECT node: display each returned expression.
    if is_select_node:
        label_lines = ["SELECT", ""]
        label_lines.extend(format_select_lines(select_clause))
        return "\n".join(label_lines)

    # Normal table nodes show the table name.
    label_lines = ["AGGREGATION" if is_result_node else table_name]

    if is_result_node:
        if group_by_value:
            label_lines.append("")
            label_lines.append(f"GROUP BY: {group_by_value}")

        # Aggregation nodes show grouping/aggregate details.
        if aggregates:
            label_lines.append("")
            label_lines.append("AGG:")
            for agg in aggregates:
                label_lines.append(f"{agg['function']}({agg['expression']})")

    return "\n".join(label_lines)


def compute_staged_layout(graph):
    """
    Compute a manual layered layout for the query graph.

    This is a custom layout function that overrides the default force-directed
    layout used by PyVis. It organizes nodes into fixed horizontal bands based
    on their role in the query execution pipeline:

        tables
        WHERE
        AGGREGATION
        ORDER BY
        SELECT
    """
    layers = {
        "tables": [],
        "filter": [],
        "agg": [],
        "order": [],
        "select": []
    }

    # Classify each node into one of the visual layers based on its metadata.
    for node, data in graph.nodes(data=True):
        if data.get("is_select_node"):
            layers["select"].append(node)
        elif data.get("is_order_node"):
            layers["order"].append(node)
        elif data.get("is_result_node"):
            layers["agg"].append(node)
        elif data.get("is_filter_node"):
            layers["filter"].append(node)
        else:
            layers["tables"].append(node)

    # Fixed vertical positions for each stage.
    y_positions = {
        "tables": 0,
        "filter": 350,
        "agg": 700,
        "order": 1050,
        "select": 1400
    }

    pos = {}

    # Spread nodes horizontally within each layer.
    for layer_name, nodes in layers.items():
        n = len(nodes)
        if n == 0:
            continue

        spacing = 550

        if n == 1:
            start_x = 0
        else:
            start_x = -((n - 1) * spacing) / 2

        for i, node in enumerate(nodes):
            x = start_x + i * spacing
            y = y_positions[layer_name]
            pos[node] = (x, y)

    return pos


def build_sql_panel_html(parsed: dict) -> str:
    """
    Build the HTML content for the color-mapped SQL panel.
    """
    clause_html = []

    select_clause = parsed.get("select", "")
    from_clause = parsed.get("from", "")
    where_clause = parsed.get("where", "")
    group_by_clause = parsed.get("group_by", "")
    order_by_clause = parsed.get("order_by", "")

    if select_clause:
        clause_html.append(
            f'<span id="clause-select" class="sql-clause select-clause">SELECT {html.escape(select_clause)}</span>'
        )

    if from_clause:
        clause_html.append(
            f'<span id="clause-from" class="sql-clause from-clause">FROM {html.escape(from_clause)}</span>'
        )

    if where_clause:
        clause_html.append(
            f'<span id="clause-where" class="sql-clause where-clause">WHERE {html.escape(where_clause)}</span>'
        )

    if group_by_clause:
        clause_html.append(
            f'<span id="clause-group_by" class="sql-clause agg-clause">GROUP BY {html.escape(group_by_clause)}</span>'
        )

    if order_by_clause:
        clause_html.append(
            f'<span id="clause-order_by" class="sql-clause order-clause">ORDER BY {html.escape(order_by_clause)}</span>'
        )

    return "<br>".join(clause_html)


def inject_demo_ui(html_content: str, parsed: dict, node_clause_map: dict, edge_clause_map: dict) -> str:
    """
    Use custom HTML/CSS/JavaScript into the HTML page PyVis generated.
    """
    sql_panel_html = build_sql_panel_html(parsed)

    custom_block = f"""
    <style>
      body {{
        font-family: Arial, sans-serif;
      }}

      .demo-top-panel {{
        width: 95%;
        margin: 0 auto 18px auto;
        padding-top: 12px;
      }}

      .sql-panel {{
        background: #ffffff;
        border: 1px solid #dddddd;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-bottom: 14px;
      }}

      .sql-title {{
        font-size: 18px;
        font-weight: 700;
        margin-bottom: 10px;
        color: #222222;
      }}

      .sql-block {{
        font-family: Monaco, monospace;
        font-size: 15px;
        line-height: 2.0;
        white-space: normal;
      }}

      .sql-clause {{
        display: inline-block;
        padding: 6px 10px;
        border-radius: 10px;
        margin: 4px 0;
        border: 2px solid transparent;
        transition: all 0.2s ease;
      }}

      .from-clause {{
        background: rgba(151, 194, 252, 0.28);
      }}

      .where-clause {{
        background: rgba(206, 142, 249, 0.28);
      }}

      .agg-clause {{
        background: rgba(255, 167, 73, 0.28);
      }}

      .order-clause {{
        background: rgba(244, 143, 177, 0.28);
      }}

      .select-clause {{
        background: rgba(129, 199, 132, 0.28);
      }}

      .sql-clause.active {{
        border-color: #222222;
        transform: scale(1.1);
        box-shadow: 0 0 0 3px rgba(0,0,0,0.08);
      }}

      .helper-note {{
        font-size: 13px;
        color: #555555;
        margin-top: 6px;
      }}
    </style>

    <div class="demo-top-panel">
      <div class="sql-panel">
        <div class="sql-title">Color-Mapped SQL</div>
        <div class="sql-block">
          {sql_panel_html}
        </div>
        <div class="helper-note">
          Hover over a node or edge in the graph to highlight the matching SQL.
        </div>
      </div>
    </div>

    <script>
      const nodeClauseMap = {node_clause_map};
      const edgeClauseMap = {edge_clause_map};

      function clearClauseHighlights() {{
        document.querySelectorAll('.sql-clause').forEach((el) => {{
          el.classList.remove('active');
        }});
      }}

      function highlightClauses(clauseIds) {{
        clearClauseHighlights();

        if (!clauseIds) return;

        clauseIds.forEach((clauseId) => {{
          const el = document.getElementById(`clause-${{clauseId}}`);
          if (el) {{
            el.classList.add('active');
          }}
        }});
      }}

      function attachGraphHoverHandlers() {{
        if (typeof network === "undefined") {{
          setTimeout(attachGraphHoverHandlers, 250);
          return;
        }}

        network.on("hoverNode", function(params) {{
          const clauses = nodeClauseMap[params.node] || [];
          highlightClauses(clauses);
        }});

        network.on("blurNode", function() {{
          clearClauseHighlights();
        }});

        network.on("hoverEdge", function(params) {{
          const clauses = edgeClauseMap[String(params.edge)] || [];
          highlightClauses(clauses);
        }});

        network.on("blurEdge", function() {{
          clearClauseHighlights();
        }});
      }}

      setTimeout(attachGraphHoverHandlers, 250);
    </script>
    """

    # Insert the custom UI block right after the opening <body> tag.
    return html_content.replace("<body>", f"<body>{custom_block}")


# Configure the Streamlit page before UI.
sl.set_page_config(page_title="PatternVis Recreation", layout="wide")

# Page title and short summary.
sl.title("PatternVis Recreation")
sl.write("Visualization of relational query structure from SQL and schema.")

# Legend for each node color.
sl.markdown("""
### Legend
- Blue ==> Table / FROM
- Purple ==> Filter / WHERE
- Orange ==> Aggregation / GROUP BY + aggregate functions
- Pink ==> ORDER BY
- Green ==> SELECT / Output
""")

# Input area for the relational schema.
schema_text = sl.text_area(
    "Schema",
    value="""Sailor(sid, sname, rating, age)
Boat(bid, bname, color)
Reserves(sid, bid, day)""",
    height=150
)

# Input area for the SQL query the user wants to visualize, initialized with a default.
query_text = sl.text_area(
    "SQL Query",
    value="""SELECT S.rating, B.color, COUNT(*), MAX(S.age)
FROM Sailor S, Reserves R, Boat B
WHERE S.sid = R.sid AND R.bid = B.bid AND S.age > 25 AND B.color = 'red'
GROUP BY S.rating, B.color
ORDER BY S.rating DESC, B.color ASC""",
    height=220
)

# Work starts when the user clicks the button.
if sl.button("Generate Visualization"):
    # Parse the schema and query.
    schema = parse_schema(schema_text)
    parsed = parse_query_basic(query_text)

    # Show the parsed schema.
    sl.subheader("Parsed Schema")
    sl.json(schema)

    # Show the parsed query structure.
    sl.subheader("Parsed Query")
    sl.json(parsed)

    # Show a natural-language explanation of the query.
    sl.subheader("Query Explanation")
    sl.write(explain_query(parsed))

    # Display quick summary stats for the query.
    stats_cols = sl.columns(5)
    stats_cols[0].metric("Tables", len(parsed.get("aliases", {})))
    stats_cols[1].metric("Joins", len(parsed.get("joins", [])))
    stats_cols[2].metric("Filters", len(parsed.get("filters", [])))
    stats_cols[3].metric("Aggregates", len(parsed.get("aggregates", [])))
    stats_cols[4].metric("Order Clauses", 1 if parsed.get("order_by") else 0)

    # Build the graph structure and compute positions for each node.
    graph = build_query_graph(parsed)
    pos = compute_staged_layout(graph)

    # Create the PyVis network.
    net = Network(
        height="1650px",
        width="100%",
        bgcolor="white",
        font_color="black",
        directed=True
    )

    # Disable physics so nodes stay fixed in the manual staged layout.
    # Enable hover and navigation controls.
    net.set_options("""
    {
      "layout": {
        "improvedLayout": false
      },
      "interaction": {
        "hover": true,
        "zoomView": true,
        "dragView": true,
        "navigationButtons": true
      },
      "physics": {
        "enabled": false
      }
    }
    """)

    # Map graph elements back to SQL clauses for hover events.
    node_clause_map = {}
    edge_clause_map = {}
    edge_counter = 0

    # Add all nodes from the NetworkX graph into the PyVis graph.
    for node, data in graph.nodes(data=True):
        table_name = data.get("table_name", node)
        filters = data.get("filters", [])
        group_by_value = data.get("group_by", "")
        aggregates = data.get("aggregates", [])
        is_result_node = data.get("is_result_node", False)
        is_select_node = data.get("is_select_node", False)
        is_filter_node = data.get("is_filter_node", False)
        is_order_node = data.get("is_order_node", False)
        select_clause = data.get("select", "")
        order_by_value = data.get("order_by", "")

        # Build hover tooltip.
        hover_text = f"Alias: {node}\nTable: {table_name}"

        if filters:
            hover_text += "\nFilters:\n" + "\n".join(filters)

        if group_by_value:
            hover_text += f"\nGroup By: {group_by_value}"

        if aggregates:
            hover_text += "\nAggregates:\n" + "\n".join(
                [f"{agg['function']}({agg['expression']})" for agg in aggregates]
            )

        if order_by_value:
            hover_text += f"\nOrder By: {order_by_value}"

        if select_clause:
            hover_text += f"\nSelect: {select_clause}"

        node_label = build_visual_label(node, data)
        x, y = pos[node]

        # Determine both the visual shape and which SQL clause(s) this node highlights when hovered.
        if is_select_node:
            node_shape = "ellipse"
            node_clause_map[node] = ["select"]
        elif is_order_node:
            node_shape = "box"
            node_clause_map[node] = ["order_by"]
        elif is_result_node:
            node_shape = "box"
            agg_clauses = []
            if parsed.get("group_by"):
                agg_clauses.append("group_by")
            if parsed.get("select"):
                agg_clauses.append("select")
            node_clause_map[node] = agg_clauses
        elif is_filter_node:
            node_shape = "box"
            node_clause_map[node] = ["where"]
        else:
            node_shape = "box"
            node_clause_map[node] = ["from"]

        net.add_node(
            node,
            label=node_label,
            title=hover_text,
            shape=node_shape,
            font={"size": 22, "color": "black", "vadjust": 0},
            margin=20,
            widthConstraint={"minimum": 220, "maximum": 320},
            color=(
                "#81C784" if is_select_node else
                "#F48FB1" if is_order_node else
                "#CE8EF9" if is_filter_node else
                "#FFA749" if is_result_node else
                "#97C2FC"
            ),
            borderWidth=2,
            x=x,
            y=y,
            physics=False
        )

    # Keep a copy of the WHERE clause text so join edges can be mapped correctly.
    where_clause_text = parsed.get("where", "")
    from_clause_text = parsed.get("from", "")

    # Add all edges from the NetworkX graph into the PyVis graph.
    for source, target, data in graph.edges(data=True):
        edge_type = data.get("label", "")
        hover_text = data.get("condition", edge_type)
        edge_id = str(edge_counter)
        edge_counter += 1

        # Determine which clause this edge should highlight when hovered.
        if edge_type == "join":
            join_condition = data.get("condition", "")
            if join_condition and join_condition in where_clause_text:
                edge_clause_map[edge_id] = ["where"]
            else:
                edge_clause_map[edge_id] = ["from"]
        elif edge_type == "filter":
            edge_clause_map[edge_id] = ["where"]
        elif edge_type == "aggregate":
            edge_clause_map[edge_id] = ["group_by", "select"] if parsed.get("group_by") else ["select"]
        elif edge_type == "order":
            edge_clause_map[edge_id] = ["order_by"]
        elif edge_type == "output":
            edge_clause_map[edge_id] = ["select"]
        else:
            edge_clause_map[edge_id] = []

        net.add_edge(
            source,
            target,
            id=edge_id,
            label=edge_type,
            title=hover_text,
            width=4,
            color=(
                "#FFA749" if edge_type == "aggregate" else
                "#CE8EF9" if edge_type == "filter" else
                "#F48FB1" if edge_type == "order" else
                "#81C784" if edge_type == "output" else
                "#97C2FC"
            ),
            font={"size": 20, "align": "middle"},
            arrows="to" if edge_type in ["filter", "aggregate", "order", "output"] else ""
        )

    # Save the PyVis graph as a temporary HTML file for Streamlit.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
        net.save_graph(tmp_file.name)
        tmp_path = tmp_file.name

    # Read the HTML, use the SQL panel and hover logic, then render the final in Streamlit.
    with open(tmp_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    html_content = inject_demo_ui(html_content, parsed, node_clause_map, edge_clause_map)

    # Set a fixed height and disable scrolling.
    components.html(html_content, height=2600, scrolling=False)

    # Clean up the temporary file after rendering.
    os.unlink(tmp_path)