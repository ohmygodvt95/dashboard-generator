"""
Filter Builder agent.

Designs filter definitions for a widget's query template.
Validates that every filter's ``param_name`` matches a
placeholder in the query, and that ``source_table`` /
``source_column`` exist in the schema when specified.
"""

import json
import re
from typing import Dict, Any, List

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a filter designer for a dashboard widget tool.
Given the SQL query template and the database schema
analysis, design appropriate interactive filters.

## Available filter types

| filter_type  | UI control            | When to use                            |
|--------------|-----------------------|----------------------------------------|
| select       | Searchable dropdown   | Categorical data with a finite set     |
| text         | Free-text input       | Arbitrary string match (LIKE / =)      |
| number       | Numeric input box     | Exact numeric value (LIMIT, year, …)   |
| date         | Single date picker    | One date bound (e.g. snapshot date)    |
| date_range   | Two date pickers      | Start + end bounds on date columns     |
| slider       | Range slider          | Bounded numeric range (price, qty, …)  |

### date_range details
Create **one** filter entry with filter_type="date_range".
The param_name is a base name (e.g. "order_date").
The system maps it to :order_date_start and :order_date_end.

This works for BOTH scenarios:
- **Same column** start/end:
  `{% if order_date_start %} AND o.orderDate >= :order_date_start {% endif %}`
  `{% if order_date_end %} AND o.orderDate <= :order_date_end {% endif %}`
- **Different columns** start/end:
  `{% if period_start %} AND o.startDate >= :period_start {% endif %}`
  `{% if period_end %} AND o.endDate <= :period_end {% endif %}`

### slider details
For slider, you MUST include a "config" object with:
  {"min": <number>, "max": <number>, "step": <number>}
Choose min/max based on realistic data ranges.

### select data source
Two options:
  Option A — Simple mode:
    Set source_table + source_column for DISTINCT values from
    a single column.
  Option B — Custom query mode:
    Set options_query to a SELECT returning "value" and "label"
    columns (for JOINs / computed labels).
    Leave source_table and source_column null.

## Return format (JSON)
{
  "filters": [
    {
      "param_name": "matches_query_placeholder",
      "label": "Human-readable label",
      "filter_type": "select|date|date_range|text|number|slider",
      "source_table": "table_name_or_null",
      "source_column": "column_name_or_null",
      "options_query": "SELECT ... AS value, ... AS label ... or null",
      "default_value": "value_or_null",
      "config": {"min": 0, "max": 100, "step": 1}
    }
  ],
  "explanation": "Short summary of filters created",
  "warnings": ["any issues detected"]
}

## Rules
1. Every param_name must match a :param_name in the query.
2. source_table / source_column must exist in the schema.
3. Do NOT create filters for params absent from the query.
4. date_range requires :param_start and :param_end placeholders.
5. options_query must be read-only SELECT with "value"+"label".
6. Use options_query for JOINs / computed labels.
7. slider MUST have config with min, max, step.
8. Choose the most appropriate filter_type for each parameter:
   - dates → date or date_range
   - status/category → select
   - counts/limits → number or slider
   - free text search → text
"""


class FilterBuilderAgent(BaseAgent):
    """Generate and validate filter definitions."""

    name = "filter_builder"
    system_prompt = PROMPT
    temperature = 0.3

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build filters for the given query template.

        Parameters:
            context (dict): Keys — ``user_message``,
                ``query_template``, ``schema_analysis``,
                ``widget_data``, ``summary``.

        Returns:
            dict: ``filters`` list, ``explanation``,
                  ``warnings``.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Query template — the main input
        query_template = context.get("query_template", "")
        if query_template:
            messages.append({
                "role": "system",
                "content": (
                    "Query template:\n"
                    f"{query_template}"
                ),
            })

        # Schema analysis for validating source_table/column
        schema_analysis = context.get("schema_analysis")
        if schema_analysis:
            messages.append({
                "role": "system",
                "content": (
                    "Schema analysis:\n"
                    f"{json.dumps(schema_analysis, indent=2)}"
                ),
            })

        # Existing filters (for modification requests)
        widget_data = context.get("widget_data")
        if widget_data and widget_data.get("filters"):
            messages.append({
                "role": "system",
                "content": (
                    "Current filters:\n"
                    f"{json.dumps(widget_data['filters'])}"
                ),
            })

        summary = context.get("summary", "")
        user_text = context.get("user_message", "")
        if summary:
            user_text = f"[Intent: {summary}]\n{user_text}"

        messages.append({"role": "user", "content": user_text})

        result = self._call_llm(messages)
        filters = result.get("filters", [])

        # --- post-validation -----------------------------------------
        warnings: List[str] = list(
            result.get("warnings", [])
        )
        if query_template:
            filters, extra_warnings = _validate_filters(
                filters,
                query_template,
                schema_analysis,
            )
            warnings.extend(extra_warnings)

        return {
            "filters": filters,
            "explanation": result.get("explanation", ""),
            "warnings": warnings,
        }


# ----- validation helpers -------------------------------------------


def _validate_filters(
    filters: List[Dict[str, Any]],
    query_template: str,
    schema_analysis: Dict[str, Any] | None,
) -> tuple:
    """
    Validate and sanitise the filter list.

    1. Remove filters whose param_name has no matching
       placeholder in the query template.
    2. Clear source_table / source_column if they don't
       exist in the schema.

    Parameters:
        filters (list[dict]): Raw filter defs from the LLM.
        query_template (str): The Jinja2 SQL template.
        schema_analysis (dict | None): Semantic schema info.

    Returns:
        tuple[list[dict], list[str]]: Cleaned filters and
            warning messages.
    """
    # Extract all :param_name placeholders from the raw
    # template (including inside {% if %} blocks).
    all_params = set(
        re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", query_template)
    )

    # Build a set of known table names from the analysis
    known_tables: set = set()
    table_columns: Dict[str, set] = {}
    if schema_analysis:
        for tbl in schema_analysis.get("tables", []):
            name = tbl.get("name", "")
            known_tables.add(name)
            cols = {
                c if isinstance(c, str) else c.get("name", "")
                for c in tbl.get("key_columns", [])
            }
            table_columns[name] = cols

    valid: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for f in filters:
        param = f.get("param_name", "")
        ftype = f.get("filter_type", "text")

        # For date_range, check _start / _end placeholders
        if ftype == "date_range":
            start_ok = f"{param}_start" in all_params
            end_ok = f"{param}_end" in all_params
            if not start_ok and not end_ok:
                warnings.append(
                    f"Filter '{param}' (date_range) has no "
                    f"matching :{param}_start / :{param}_end "
                    "in the query — removed."
                )
                continue
        else:
            if param and param not in all_params:
                warnings.append(
                    f"Filter '{param}' has no matching "
                    f":{param} in the query — removed."
                )
                continue

        # Validate source_table / source_column
        src_table = f.get("source_table")
        src_col = f.get("source_column")
        if src_table and src_table not in known_tables:
            warnings.append(
                f"Filter '{param}': source_table "
                f"'{src_table}' not found — cleared."
            )
            f["source_table"] = None
            f["source_column"] = None

        valid.append(f)

    return valid, warnings
