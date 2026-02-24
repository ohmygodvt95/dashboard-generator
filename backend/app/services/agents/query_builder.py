"""
Query Builder agent.

Generates Jinja2-enhanced SQL query templates based on the
user's request, the semantic schema analysis, and the current
widget state.  Produces clean, safe, read-only queries with
conditional filter blocks.
"""

import json
from typing import Dict, Any

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a SQL query builder for a dashboard widget tool.
Given the user's request, a database schema analysis, and
the current widget state, produce (or modify) an SQL query
template.

CRITICAL — Jinja2 template rules:
1. Start the WHERE clause with  WHERE 1=1
2. Wrap each optional filter in Jinja2 conditional blocks:
   {%% if param_name %%} AND column = :param_name {%% endif %%}
3. For date_range filters use TWO conditions:
   {%% if date_start %%} AND col >= :date_start {%% endif %%}
   {%% if date_end %%}   AND col <= :date_end   {%% endif %%}
4. Parameters inside SQL use :param_name (colon prefix).
5. The query MUST return valid data even when NO filters are
   applied (all conditionals stripped out).
6. Conditional JOINs are allowed:
   {%% if some_param %%} JOIN ... {%% endif %%}
7. LIMIT is also allowed:
   {%% if limit %%} LIMIT :limit {%% endif %%}

Safety rules:
- Only SELECT queries — never DROP, DELETE, UPDATE, INSERT.
- Always include GROUP BY / ORDER BY when aggregating.
- Use table aliases for readability.
- Prefer explicit JOIN over implicit comma joins.
- Use DATE_FORMAT or equivalent for date grouping.

Return a JSON object:
{
  "query_template": "SELECT ... (the full Jinja2 SQL)",
  "explanation": "Short human-readable explanation",
  "output_columns": [
    {"name": "col_alias", "type": "string|number|date"}
  ]
}

output_columns describes what the query returns — this is
used by the chart builder to map axes.
If the user asks to MODIFY the existing query, keep
unchanged parts intact and only alter what is requested.
"""


class QueryBuilderAgent(BaseAgent):
    """Build or modify Jinja2 SQL query templates."""

    name = "query_builder"
    system_prompt = PROMPT
    temperature = 0.4

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate or update a query template.

        Parameters:
            context (dict): Keys — ``user_message``,
                ``schema_analysis``, ``widget_data``,
                ``chat_history``, ``summary``.

        Returns:
            dict: ``query_template``, ``explanation``,
                  ``output_columns``.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Schema analysis context
        schema_analysis = context.get("schema_analysis")
        if schema_analysis:
            messages.append({
                "role": "system",
                "content": (
                    "Database schema analysis:\n"
                    f"{json.dumps(schema_analysis, indent=2)}"
                ),
            })

        # Current widget snapshot
        widget_data = context.get("widget_data")
        if widget_data:
            current_query = widget_data.get(
                "query_template", ""
            )
            if current_query:
                messages.append({
                    "role": "system",
                    "content": (
                        "Current query template:\n"
                        f"{current_query}"
                    ),
                })

        # Recent chat (short — query builder doesn't need
        # full history, only the latest intent summary).
        for msg in context.get("chat_history", [])[-4:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        # User request with the analyser's summary
        summary = context.get("summary", "")
        user_text = context["user_message"]
        if summary:
            user_text = f"[Intent: {summary}]\n{user_text}"

        messages.append({"role": "user", "content": user_text})

        result = self._call_llm(messages)
        return {
            "query_template": result.get(
                "query_template", ""
            ),
            "explanation": result.get("explanation", ""),
            "output_columns": result.get(
                "output_columns", []
            ),
        }
