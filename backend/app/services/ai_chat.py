"""
AI chat service for widget configuration.

Uses OpenAI API to process natural language requests and
generate chart configurations, SQL queries, and filter
definitions for widgets.
"""

import json
from typing import List, Dict, Any, Optional
from openai import OpenAI

from app.config import settings


SYSTEM_PROMPT = """You are a chart/dashboard widget builder AI assistant. \
Your job is to help users create data visualizations by generating SQL \
queries and chart configurations based on their database schema.

When the user describes a chart they want, you must respond with a JSON \
object containing the widget configuration. Always respond with valid JSON \
in the following format:

{
  "message": "Human-readable explanation of what you created/changed",
  "widget_update": {
    "chart_type": "bar|line|pie|doughnut|area|scatter",
    "query_template": "SELECT ... FROM ... WHERE ...",
    "chart_config": {
      "x_axis": "column_name_for_x",
      "y_axis": "column_name_for_y",
      "colors": ["#hex1", "#hex2"],
      "title": {"display": true, "text": "Chart Title"},
      "legend": {"display": true, "position": "top"},
      "indexAxis": "x"
    }
  },
  "filters": [
    {
      "param_name": "param_name_matching_query_placeholder",
      "label": "Display Label",
      "filter_type": "select|date|date_range|text|number",
      "source_table": "table_name_or_null",
      "source_column": "column_name_or_null",
      "default_value": "default_or_null"
    }
  ]
}

Query Template Rules (CRITICAL - uses Jinja2 syntax):
1. Use Jinja2 conditional blocks to make filters optional:
   WHERE 1=1
   {%% if status %%} AND status = :status {%% endif %%}
   {%% if date_start %%} AND created_at >= :date_start {%% endif %%}
   {%% if date_end %%} AND created_at <= :date_end {%% endif %%}
2. Always start WHERE clause with "WHERE 1=1" so conditionals \
   can all use "AND ..."
3. SQL parameters use :param_name syntax (colon prefix)
4. Wrap each filter condition in {%% if param_name %%} ... {%% endif %%}
5. For date_range filters, use TWO separate conditions:
   {%% if date_start %%} AND col >= :date_start {%% endif %%}
   {%% if date_end %%} AND col <= :date_end {%% endif %%}
6. Without filters selected, the query MUST still return valid data
7. Conditional JOINs and LIMIT are also supported:
   {%% if limit %%} LIMIT :limit {%% endif %%}

General Rules:
1. Always use appropriate GROUP BY, ORDER BY clauses
2. Suggest relevant filters based on the schema
3. Use clear, descriptive chart titles
4. Choose appropriate chart types for the data
5. If the user asks to modify, only change what they request
6. Keep SQL queries safe - no DROP, DELETE, UPDATE, INSERT etc.
7. Always respond with the JSON format above, even for conversational \
   messages. Put your explanation in the "message" field.

Example query_template:
  SELECT DATE_FORMAT(o.orderDate, '%%Y-%%m') AS month, \
SUM(od.quantityOrdered * od.priceEach) AS revenue
  FROM orders o
  JOIN orderdetails od ON o.orderNumber = od.orderNumber
  WHERE 1=1
  {%% if date_start %%} AND o.orderDate >= :date_start {%% endif %%}
  {%% if date_end %%} AND o.orderDate <= :date_end {%% endif %%}
  {%% if status %%} AND o.status = :status {%% endif %%}
  GROUP BY month
  ORDER BY month
"""


def build_schema_context(schema: Optional[Dict] = None) -> str:
    """
    Build a context string from the database schema for the AI.

    Parameters:
        schema (dict, optional): Database schema from introspection.

    Returns:
        str: Formatted schema description for the AI prompt.
    """
    if not schema or not schema.get("tables"):
        return "No database schema available yet."

    lines = [f"Database: {schema.get('database', 'unknown')}"]
    lines.append("Tables:")
    for table in schema["tables"]:
        cols = ", ".join(
            f"{c['name']} ({c['type']})"
            for c in table.get("columns", [])
        )
        lines.append(f"  - {table['name']}: {cols}")
    return "\n".join(lines)


def build_widget_context(widget_data: Optional[Dict] = None) -> str:
    """
    Build a context string from the current widget configuration.

    Parameters:
        widget_data (dict, optional): Current widget configuration.

    Returns:
        str: Formatted widget description for the AI prompt.
    """
    if not widget_data:
        return "No widget configuration yet (new widget)."

    parts = [f"Current widget: {widget_data.get('name', '')}"]
    if widget_data.get("chart_type"):
        parts.append(f"Chart type: {widget_data['chart_type']}")
    if widget_data.get("query_template"):
        parts.append(
            f"Current query: {widget_data['query_template']}"
        )
    if widget_data.get("chart_config"):
        parts.append(
            f"Chart config: {json.dumps(widget_data['chart_config'])}"
        )
    return "\n".join(parts)


def chat_with_ai(
    user_message: str,
    chat_history: List[Dict[str, str]],
    schema: Optional[Dict] = None,
    widget_data: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Send a message to the AI and get a widget configuration response.

    Builds context from the database schema and current widget state,
    then sends the conversation to OpenAI for processing.

    Parameters:
        user_message (str): The user's natural language request.
        chat_history (list[dict]): Previous conversation messages.
        schema (dict, optional): Database schema information.
        widget_data (dict, optional): Current widget configuration.

    Returns:
        dict: Parsed AI response with message, widget_update,
              and filters.
    """
    client = OpenAI(api_key=settings.openai_api_key)

    schema_context = build_schema_context(schema)
    widget_context = build_widget_context(widget_data)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Database Schema:\n{schema_context}\n\n"
                f"Widget State:\n{widget_context}"
            ),
        },
    ]

    # Add chat history (last 20 messages max)
    for msg in chat_history[-20:]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)
        return parsed
    except json.JSONDecodeError:
        # If AI doesn't return valid JSON, wrap the response
        return {
            "message": content,
            "widget_update": None,
            "filters": [],
        }
    except Exception as e:
        return {
            "message": f"AI service error: {str(e)}",
            "widget_update": None,
            "filters": [],
        }
