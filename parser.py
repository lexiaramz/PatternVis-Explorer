"""
parser.py

Lightweight SQL and schema parsing utilities for PatternVis.

parser.py is responsible for:
- extracting aggregate functions from SELECT clauses
- parsing FROM, WHERE, GROUP BY, and ORDER BY clauses into their components
- parsing a simple schema text format into a dictionary
- assembling a parsed query dictionary for later use by graph_builder.py and app.py
- generating a natural-language explanation of the parsed query

Important note:
It is not a full SQL parser and will not correctly handle all
valid SQL syntax, nested queries, complex expressions, or edge cases.
"""

import re


def extract_aggregates(select_clause: str) -> list:
    """
    Extract common aggregate functions from a SELECT clause.
    """
    aggregates = []

    if not select_clause:
        return aggregates

    pattern = r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\((.*?)\)"
    matches = re.findall(pattern, select_clause, flags=re.IGNORECASE)

    for func, expr in matches:
        aggregates.append({
            "function": func.upper(),
            "expression": expr.strip()
        })

    return aggregates


def parse_from_clause(from_clause: str):
    """
    Parse the FROM clause into tables, aliases, and JOIN ... ON conditions.
    """
    tables = []
    aliases = {}
    joins_from_on = []

    if not from_clause:
        return tables, aliases, joins_from_on

    # Normalize whitespace.
    from_clause = " ".join(from_clause.strip().split())

    # Case 1: explicit JOIN syntax
    if re.search(r"\bJOIN\b", from_clause, flags=re.IGNORECASE):
        parts = re.split(r"\bJOIN\b", from_clause, flags=re.IGNORECASE)

        # Parse the first table that appears before the first JOIN.
        first_part = parts[0].strip()
        first_tokens = first_part.split()

        if len(first_tokens) == 1:
            table_name = first_tokens[0]
            alias = table_name
        elif len(first_tokens) == 2:
            table_name, alias = first_tokens
        elif len(first_tokens) == 3 and first_tokens[1].upper() == "AS":
            table_name = first_tokens[0]
            alias = first_tokens[2]
        else:
            table_name = None
            alias = None

        if table_name and alias:
            tables.append(table_name)
            aliases[alias] = table_name

        # Parse each subsequent JOIN segment.
        for part in parts[1:]:
            split_on = re.split(r"\bON\b", part, flags=re.IGNORECASE)
            table_part = split_on[0].strip()
            on_part = split_on[1].strip() if len(split_on) > 1 else ""

            table_tokens = table_part.split()

            if len(table_tokens) == 1:
                table_name = table_tokens[0]
                alias = table_name
            elif len(table_tokens) == 2:
                table_name, alias = table_tokens
            elif len(table_tokens) == 3 and table_tokens[1].upper() == "AS":
                table_name = table_tokens[0]
                alias = table_tokens[2]
            else:
                continue

            tables.append(table_name)
            aliases[alias] = table_name

            # Save the ON condition separately to be treated like a join edge in the graph.
            if on_part:
                joins_from_on.append(on_part)

    # Case 2: comma-separated tables
    else:
        parts = [part.strip() for part in from_clause.split(",")]

        for part in parts:
            tokens = part.split()

            if len(tokens) == 1:
                table_name = tokens[0]
                alias = table_name
            elif len(tokens) == 2:
                table_name, alias = tokens
            elif len(tokens) == 3 and tokens[1].upper() == "AS":
                table_name = tokens[0]
                alias = tokens[2]
            else:
                continue

            tables.append(table_name)
            aliases[alias] = table_name

    return tables, aliases, joins_from_on


def parse_where_clause(where_clause: str):
    """
    Parse the WHERE clause into join conditions and filter conditions.
    """
    joins = []
    filters = []

    if not where_clause:
        return joins, filters

    conditions = [cond.strip() for cond in re.split(r"\bAND\b", where_clause, flags=re.IGNORECASE)]

    for cond in conditions:
        if "=" in cond:
            left, right = [x.strip() for x in cond.split("=", 1)]

            # Conditions like S.sid = R.sid are treated as joins.
            if "." in left and "." in right:
                joins.append({
                    "left": left,
                    "right": right,
                    "condition": cond
                })
            else:
                filters.append(cond)
        else:
            filters.append(cond)

    return joins, filters


def parse_schema(schema_text: str) -> dict:
    """
    Parse a simple schema description format into a dictionary.
    """
    schema = {}

    lines = [line.strip() for line in schema_text.splitlines() if line.strip()]

    for line in lines:
        match = re.match(r"(\w+)\s*\((.*?)\)", line)
        if match:
            table_name = match.group(1)
            columns = [col.strip() for col in match.group(2).split(",")]
            schema[table_name] = columns

    return schema


def parse_query_basic(query: str) -> dict:
    """
    Parse a simplified SQL query into major clause components.
    """
    # Normalize whitespace.
    query_clean = " ".join(query.strip().split())
    query_upper = query_clean.upper()

    result = {
        "select": "",
        "from": "",
        "where": "",
        "group_by": "",
        "order_by": "",
        "tables": [],
        "aliases": {},
        "joins": [],
        "filters": [],
        "aggregates": []
    }

    # Locate clause boundaries using uppercase copies for case-insensitive searching.
    select_start = query_upper.find("SELECT ")
    from_start = query_upper.find(" FROM ")
    where_start = query_upper.find(" WHERE ")
    group_by_start = query_upper.find(" GROUP BY ")
    order_by_start = query_upper.find(" ORDER BY ")

    if select_start != -1 and from_start != -1:
        result["select"] = query_clean[select_start + 7:from_start].strip()

    if from_start != -1:
        clause_end_positions = [pos for pos in [where_start, group_by_start, order_by_start] if pos != -1]
        first_clause_start = min(clause_end_positions) if clause_end_positions else len(query_clean)
        result["from"] = query_clean[from_start + 6:first_clause_start].strip()

    if where_start != -1:
        where_end_positions = [pos for pos in [group_by_start, order_by_start] if pos != -1 and pos > where_start]
        where_end = min(where_end_positions) if where_end_positions else len(query_clean)
        result["where"] = query_clean[where_start + 7:where_end].strip()

    if group_by_start != -1:
        group_by_end_positions = [pos for pos in [order_by_start] if pos != -1 and pos > group_by_start]
        group_by_end = min(group_by_end_positions) if group_by_end_positions else len(query_clean)
        result["group_by"] = query_clean[group_by_start + 10:group_by_end].strip()

    if order_by_start != -1:
        result["order_by"] = query_clean[order_by_start + 10:].strip()

    # Parse the FROM clause first.
    result["tables"], result["aliases"], joins_from_on = parse_from_clause(result["from"])

    # Parse the WHERE clause separately to split out join conditions from regular filter conditions.
    where_joins, result["filters"] = parse_where_clause(result["where"])
    result["joins"] = []

    # Convert JOIN ... ON conditions into the same join dictionary format.
    for cond in joins_from_on:
        if "=" in cond:
            left, right = [x.strip() for x in cond.split("=", 1)]
            if "." in left and "." in right:
                result["joins"].append({
                    "left": left,
                    "right": right,
                    "condition": cond
                })

    # Merge joins found in WHERE with joins found in JOIN ... ON syntax.
    result["joins"].extend(where_joins)

    # Extract aggregate functions from the SELECT clause.
    result["aggregates"] = extract_aggregates(result["select"])

    return result


def explain_query(parsed: dict) -> str:
    """
    Generate a simple natural-language explanation of a parsed query.
    """
    aliases = parsed["aliases"]
    joins = parsed["joins"]
    filters = parsed["filters"]
    select = parsed["select"]
    group_by = parsed["group_by"]
    order_by = parsed["order_by"]
    aggregates = parsed["aggregates"]

    explanation = "This query"

    if select:
        cleaned = select.replace(".", " ")
        explanation += f" retrieves {cleaned}"

    table_names = list(aliases.values())
    if table_names:
        explanation += f" from the {' and '.join(table_names)} table(s)"

    if joins:
        join_phrases = []
        for j in joins:
            left = j["left"].split(".")[0]
            right = j["right"].split(".")[0]
            join_phrases.append(f"{left} and {right}")
        explanation += f" by joining {' and '.join(join_phrases)}"

    if filters:
        explanation += f" with conditions {' and '.join(filters)}"

    if group_by:
        explanation += f", grouped by {group_by}"

    if aggregates:
        agg_text = ", ".join(
            [f"{agg['function']} of {agg['expression']}" for agg in aggregates]
        )
        explanation += f", and calculates {agg_text}"

    if order_by:
        explanation += f", then orders the results by {order_by}"

    explanation += "."

    return explanation