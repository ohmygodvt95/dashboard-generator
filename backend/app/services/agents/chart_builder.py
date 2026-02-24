"""
Chart / UI Builder agent.

Selects the best chart type and produces a chart_config
object compatible with Chart.js (via react-chartjs-2).
"""

import json
from typing import Dict, Any

from app.services.agents.base import BaseAgent


PROMPT = """\
You are a data-visualisation expert for a Chart.js dashboard
widget builder.  Given the SQL query's output columns, the
user's request, and the current widget state, choose the
optimal chart type and produce a chart_config.

Supported chart types:
  bar, line, pie, doughnut, area, scatter

Return a JSON object:
{
  "chart_type": "bar|line|pie|doughnut|area|scatter",
  "chart_config": {
    "x_axis": "column_name_for_x_axis",
    "y_axis": "column_name_for_y_axis",
    "colors": ["#4F46E5", "#10B981", "#F59E0B", "#EF4444"],
    "title": {
      "display": true,
      "text": "Descriptive Chart Title"
    },
    "legend": {
      "display": true,
      "position": "top"
    },
    "indexAxis": "x"
  },
  "explanation": "Why this chart type and config was chosen"
}

Guidelines:
1. Time-series data → line or area chart.
2. Categorical comparison → bar chart (horizontal if many
   categories: set indexAxis="y").
3. Part-of-whole → pie or doughnut.
4. Two numeric axes → scatter.
5. x_axis / y_axis must match column aliases returned by the
   SQL query.
6. Provide 4-8 pleasant colours (hex) that work well together.
7. Title text should be concise and descriptive.
8. If the user asks to change only the chart style, keep
   x_axis / y_axis from the current config unless the query
   changed too.
"""


class ChartBuilderAgent(BaseAgent):
    """Choose chart type and build Chart.js config."""

    name = "chart_builder"
    system_prompt = PROMPT
    temperature = 0.5

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate or update chart configuration.

        Parameters:
            context (dict): Keys — ``user_message``,
                ``output_columns``, ``widget_data``,
                ``chat_history``, ``summary``.

        Returns:
            dict: ``chart_type``, ``chart_config``,
                  ``explanation``.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]

        # Output columns from the query builder
        output_columns = context.get("output_columns", [])
        if output_columns:
            messages.append({
                "role": "system",
                "content": (
                    "Query output columns:\n"
                    f"{json.dumps(output_columns)}"
                ),
            })

        # Current widget state (for modification requests)
        widget_data = context.get("widget_data")
        if widget_data:
            current = {}
            if widget_data.get("chart_type"):
                current["chart_type"] = widget_data["chart_type"]
            if widget_data.get("chart_config"):
                current["chart_config"] = (
                    widget_data["chart_config"]
                )
            if current:
                messages.append({
                    "role": "system",
                    "content": (
                        "Current chart configuration:\n"
                        f"{json.dumps(current, indent=2)}"
                    ),
                })

        # Recent chat for context on modification intent
        for msg in context.get("chat_history", [])[-4:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        summary = context.get("summary", "")
        user_text = context.get("user_message", "")
        if summary:
            user_text = f"[Intent: {summary}]\n{user_text}"

        messages.append({"role": "user", "content": user_text})

        result = self._call_llm(messages)
        return {
            "chart_type": result.get("chart_type", "bar"),
            "chart_config": result.get("chart_config", {}),
            "explanation": result.get("explanation", ""),
        }
