"""
graph_builder.py

Graph construction logic for PatternVis.

graph_builder.py converts the parsed SQL representation into a NetworkX graph.

This graph is later rendered visually in app.py.
"""

import networkx as nw


def group_filters_by_alias(filters: list[str]) -> dict:
    """
    Group filter conditions by the table alias they reference.
    """
    filters_by_alias = {}

    for filt in filters:
        filt = filt.strip()

        # Only group filters that clearly reference an alias.column.
        if "." in filt:
            alias = filt.split(".", 1)[0].strip()
            filters_by_alias.setdefault(alias, []).append(filt)

    return filters_by_alias


def build_query_graph(parsed: dict) -> nw.Graph:
    """
    Build a staged query graph from a parsed SQL dictionary.
    """
    graph = nw.Graph()

    aliases = parsed["aliases"]
    filters = parsed.get("filters", [])
    filters_by_alias = group_filters_by_alias(filters)

    # Add one node per table alias found in the FROM clause, with that alias stored for tooltip/context use.
    for alias, table_name in aliases.items():
        graph.add_node(
            alias,
            table_name=table_name,
            filters=filters_by_alias.get(alias, [])
        )

    # Add join edges between table aliases.
    for join in parsed["joins"]:
        left_alias = join["left"].split(".")[0]
        right_alias = join["right"].split(".")[0]

        graph.add_edge(
            left_alias,
            right_alias,
            label="join",
            condition=join["condition"]
        )

    # Add additional nodes for WHERE filters, GROUP BY, ORDER BY, and SELECT output as needed.
    group_by_value = parsed.get("group_by", "")
    aggregates = parsed.get("aggregates", [])
    select_clause = parsed.get("select", "")
    order_by_value = parsed.get("order_by", "")

    # Determine which stages are present in the query to know which nodes to add.
    has_filters = len(filters) > 0
    has_aggregation = bool(group_by_value or aggregates)
    has_order_by = bool(order_by_value)

    # Track the most recent stage node so subsequent stages can connect correctly.
    current_stage_node = None

    # Add a WHERE node if the query has non-join filter conditions.
    if has_filters:
        graph.add_node(
            "FILTER_NODE",
            table_name="WHERE",
            filters=filters,
            is_filter_node=True
        )

        # All table aliases point into the filter stage.
        for alias in aliases.keys():
            graph.add_edge(alias, "FILTER_NODE", label="filter")

        current_stage_node = "FILTER_NODE"

    # Add an aggregation node if GROUP BY or aggregate functions exist.
    if has_aggregation:
        graph.add_node(
            "AGG_RESULT",
            table_name="AGGREGATION",
            filters=[],
            group_by=group_by_value,
            aggregates=aggregates,
            is_result_node=True
        )

        if current_stage_node:
            graph.add_edge(current_stage_node, "AGG_RESULT", label="aggregate")
        else:
            for alias in aliases.keys():
                graph.add_edge(alias, "AGG_RESULT", label="aggregate")

        current_stage_node = "AGG_RESULT"

    # Add an ORDER BY node if the query sorts results.
    if has_order_by:
        graph.add_node(
            "ORDER_NODE",
            table_name="ORDER BY",
            filters=[],
            order_by=order_by_value,
            is_order_node=True
        )

        if current_stage_node:
            graph.add_edge(current_stage_node, "ORDER_NODE", label="order")
        else:
            for alias in aliases.keys():
                graph.add_edge(alias, "ORDER_NODE", label="order")

        current_stage_node = "ORDER_NODE"

    # Add a final SELECT/output node if there is a SELECT clause.
    if select_clause:
        graph.add_node(
            "SELECT_NODE",
            table_name="SELECT",
            filters=[],
            select=select_clause,
            is_select_node=True
        )

        if current_stage_node:
            graph.add_edge(current_stage_node, "SELECT_NODE", label="output")
        else:
            for alias in aliases.keys():
                graph.add_edge(alias, "SELECT_NODE", label="output")

    return graph